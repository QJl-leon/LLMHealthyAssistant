from pathlib import Path
from dotenv import load_dotenv
_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_ROOT / '.env')
