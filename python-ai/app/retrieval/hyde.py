from __future__ import annotations
import logging
import os
import re
logger = logging.getLogger(__name__)
HYDE_MODEL = os.getenv('HYDE_MODEL', '')
HYDE_MAX_TOKENS = int(os.getenv('HYDE_MAX_TOKENS', '160'))
HYDE_TTL_SECONDS = int(os.getenv('CACHE_TTL_HYDE', '86400'))
HYDE_NUM = int(os.getenv('HYDE_NUM', '1'))
HYDE_DEFAULT_ON = os.getenv('HYDE_ENABLED', 'false').lower() in ('1', 'true', 'yes')
_NUM_RE = re.compile('\\d+(?:\\.\\d+)?')
_HYDE_PROMPT = '你是健康与运动医学资料员。针对下面的用户问题，写一段「运动医学指南或健康论文里可能出现的原文片段」。\n硬性要求：\n1) 若问题中出现具体指标名（如「低密度脂蛋白」）或健康主题，必须原样使用该名称；\n2) 描述它的临床意义、与运动 / 生活方式的关系、干预方向与注意事项；\n3) **严禁出现任何具体数字**（指标结果值、参考区间、运动强度/时长/频率/剂量、标准号、年份）——一律用「参考区间以内」「需循序渐进」「有强度上限」这类表述代替；\n4) 采用资料风格：主题 | 指标：… | 干预方向：… | 注意事项：…；\n5) 60~120 字，中文，不要 markdown，不要直接回答问题。\n\n用户问题：{query}'

def strip_numbers(text: str) -> str:
    return _NUM_RE.sub('某值', text or '')

def should_use_hyde(query: str) -> bool:
    q = (query or '').strip()
    if not q or len(q) > 30:
        return False
    if re.search('\\d', q):
        return False
    return True

def _generate_uncached(query: str) -> str:
    from app.gateway.adapters.llm import LLMAdapter
    llm = LLMAdapter()
    if HYDE_MODEL:
        llm.model = HYDE_MODEL
    resp = llm.chat(messages=[{'role': 'user', 'content': _HYDE_PROMPT.format(query=query)}], temperature=0.3, max_tokens=HYDE_MAX_TOKENS)
    return str(resp.get('choices', [{}])[0].get('message', {}).get('content', '')).strip()

def build_hyde_query(query: str, cache=None) -> str:
    from app.cache import get_cache, hyde_key
    cache = cache or get_cache()
    model = HYDE_MODEL or os.getenv('LLM_MODEL', 'deepseek-chat')
    key = hyde_key(query, model)
    if cache.enabled:
        hit = cache.get(key)
        if hit:
            return str(hit)
    try:
        text = _generate_uncached(query)
        text = strip_numbers(text)
        if len(text) < 10:
            logger.warning('[HyDE] 生成文本过短，回退原 query: %r', text[:50])
            return query
        if cache.enabled:
            cache.set(key, text, ttl=HYDE_TTL_SECONDS)
        logger.info('[HyDE] 已生成假设文档 %d 字: %s', len(text), text[:60])
        return text
    except Exception as e:
        logger.warning('[HyDE] 生成失败，回退原 query: %s', e)
        return query

def build_hyde_queries(query: str, n: int=3, cache=None) -> list[str]:
    if n <= 1:
        return [build_hyde_query(query, cache=cache)]
    texts = []
    for i in range(n):
        try:
            text = strip_numbers(_generate_uncached(query))
            if len(text) >= 10:
                texts.append(text)
        except Exception as e:
            logger.warning('[HyDE] 第 %d 条生成失败: %s', i + 1, e)
    return texts or [query]

def prepare_dense_query(query: str, enabled: bool | None=None, num: int | None=None):
    if enabled is None:
        enabled = HYDE_DEFAULT_ON
    if not enabled or not should_use_hyde(query):
        return (query, None)
    n = HYDE_NUM if num is None else num
    if n <= 1:
        return (build_hyde_query(query), None)
    docs = build_hyde_queries(query, n=n)
    try:
        from app.gateway.adapters.embedding import EmbeddingAdapter
        vectors = EmbeddingAdapter().embed(docs)
        if not vectors or len(vectors) < 2:
            return (docs[0] if docs else query, None)
        dim = len(vectors[0])
        avg = [sum((v[i] for v in vectors)) / len(vectors) for i in range(dim)]
        logger.info('[HyDE] multi-HyDE 已生成 %d 条并取平均向量（dim=%d）', len(vectors), dim)
        return (docs[0], avg)
    except Exception as e:
        logger.warning('[HyDE] 多视角向量平均失败，回退单条 HyDE: %s', e)
        return (docs[0] if docs else query, None)
