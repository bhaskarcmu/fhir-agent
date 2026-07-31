package com.healthcare.epic.auth;

import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;

/**
 * Issues and validates short-lived opaque bearer tokens (design.md &sect;4: "JWT or opaque,
 * backed by an in-memory store" — opaque chosen here so validating a token never requires this
 * service to hold or re-derive a signing key of its own).
 */
@Component
public class AccessTokenStore {

    private record Issued(String clientId, Instant expiresAt) {}

    private final Map<String, Issued> tokens = new ConcurrentHashMap<>();
    private final SecureRandom random = new SecureRandom();
    private final long ttlSeconds;

    public AccessTokenStore(AuthProperties properties) {
        this.ttlSeconds = properties.getTokenTtlSeconds();
    }

    public String issue(String clientId) {
        byte[] bytes = new byte[32];
        random.nextBytes(bytes);
        String token = Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
        tokens.put(token, new Issued(clientId, Instant.now().plusSeconds(ttlSeconds)));
        return token;
    }

    public long ttlSeconds() {
        return ttlSeconds;
    }

    /** Empty if the token is missing, or was issued but has since expired. */
    public Optional<String> validate(String token) {
        Issued issued = tokens.get(token);
        if (issued == null) {
            return Optional.empty();
        }
        if (Instant.now().isAfter(issued.expiresAt())) {
            tokens.remove(token);
            return Optional.empty();
        }
        return Optional.of(issued.clientId());
    }
}
