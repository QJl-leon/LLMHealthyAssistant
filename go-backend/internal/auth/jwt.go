
package auth

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"strings"
	"time"
)

type JWTClaims struct {
	Subject  string   `json:"sub"`
	TenantID string   `json:"tenant_id"`
	Role     string   `json:"role,omitempty"`
	Scopes   []string `json:"scopes,omitempty"`
	IssuedAt int64    `json:"iat"`
	Expires  int64    `json:"exp"`
}

func SignJWT(secret []byte, claims JWTClaims) (string, error) {
	header := base64.RawURLEncoding.EncodeToString(
		[]byte(`{"alg":"HS256","typ":"JWT"}`),
	)

	payloadBytes, err := json.Marshal(claims)
	if err != nil {
		return "", fmt.Errorf("marshal claims: %w", err)
	}
	payload := base64.RawURLEncoding.EncodeToString(payloadBytes)

	signingInput := header + "." + payload
	sig := signHMAC(secret, signingInput)
	signature := base64.RawURLEncoding.EncodeToString(sig)

	return signingInput + "." + signature, nil
}

func VerifyJWT(secret []byte, token string) (JWTClaims, error) {
	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		return JWTClaims{}, fmt.Errorf("invalid token format")
	}

	signingInput := parts[0] + "." + parts[1]
	expectedSig, err := base64.RawURLEncoding.DecodeString(parts[2])
	if err != nil {
		return JWTClaims{}, fmt.Errorf("invalid signature encoding")
	}
	actualSig := signHMAC(secret, signingInput)
	if !hmac.Equal(expectedSig, actualSig) {
		return JWTClaims{}, fmt.Errorf("invalid signature")
	}

	payloadBytes, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		return JWTClaims{}, fmt.Errorf("invalid payload encoding")
	}
	var claims JWTClaims
	if err := json.Unmarshal(payloadBytes, &claims); err != nil {
		return JWTClaims{}, fmt.Errorf("invalid payload json: %w", err)
	}

	if claims.Expires > 0 && time.Now().Unix() > claims.Expires {
		return JWTClaims{}, fmt.Errorf("token expired")
	}

	return claims, nil
}

func NewUserToken(secret []byte, userID, tenantID, role string, ttl time.Duration, scopes ...string) (string, error) {
	if ttl <= 0 {
		ttl = 24 * time.Hour
	}
	if role == "" {
		role = "user"
	}
	now := time.Now()
	return SignJWT(secret, JWTClaims{
		Subject:  userID,
		TenantID: tenantID,
		Role:     role,
		Scopes:   scopes,
		IssuedAt: now.Unix(),
		Expires:  now.Add(ttl).Unix(),
	})
}

func signHMAC(secret []byte, message string) []byte {
	mac := hmac.New(sha256.New, secret)
	mac.Write([]byte(message))
	return mac.Sum(nil)
}
