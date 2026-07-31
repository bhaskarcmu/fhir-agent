package com.healthcare.epic.auth;

import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.crypto.RSASSAVerifier;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
import java.text.ParseException;
import java.time.Instant;
import java.util.Date;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;

/**
 * Validates a SMART Backend Services JWT client assertion (RFC 7523 client-credentials grant):
 * signature against the registered client's public key, {@code iss}/{@code sub} identify a known
 * client, {@code aud} matches this token endpoint, {@code exp} is not expired, and {@code jti} has
 * not been replayed.
 *
 * <p><b>Known simplification:</b> only {@code RS384} is supported. The spec also allows
 * {@code ES384} (EC keys) — left out here to avoid a second key-handling path for M2; worth
 * revisiting if a real Epic sandbox test ever requires it (see {@code docs/phase4/design.md} §7).
 */
@Component
public class ClientAssertionValidator {

    public sealed interface Result {
        record Valid(String clientId) implements Result {}

        record Invalid(String error, String errorDescription) implements Result {}
    }

    private final ClientRegistry registry;
    private final String expectedAudience;
    private final Set<String> usedJtis = ConcurrentHashMap.newKeySet();

    public ClientAssertionValidator(ClientRegistry registry, AuthProperties properties) {
        this.registry = registry;
        this.expectedAudience = properties.getTokenEndpoint();
    }

    public Result validate(String clientAssertion) {
        SignedJWT jwt;
        try {
            jwt = SignedJWT.parse(clientAssertion);
        } catch (ParseException e) {
            return new Result.Invalid(
                    "invalid_request", "client_assertion is not a well-formed JWT");
        }

        if (!JWSAlgorithm.RS384.equals(jwt.getHeader().getAlgorithm())) {
            return new Result.Invalid("invalid_client", "client_assertion must be signed RS384");
        }

        JWTClaimsSet claims;
        try {
            claims = jwt.getJWTClaimsSet();
        } catch (ParseException e) {
            return new Result.Invalid("invalid_request", "client_assertion claims are malformed");
        }

        String issuer = claims.getIssuer();
        String subject = claims.getSubject();
        if (issuer == null || !issuer.equals(subject)) {
            return new Result.Invalid(
                    "invalid_client", "iss and sub must match and identify the client");
        }

        Optional<RSAKey> publicKey = registry.find(issuer);
        if (publicKey.isEmpty()) {
            return new Result.Invalid("invalid_client", "unknown client: " + issuer);
        }

        try {
            RSASSAVerifier verifier = new RSASSAVerifier(publicKey.get().toRSAPublicKey());
            if (!jwt.verify(verifier)) {
                return new Result.Invalid(
                        "invalid_client", "client_assertion signature does not verify");
            }
        } catch (Exception e) {
            return new Result.Invalid(
                    "invalid_client", "client_assertion signature could not be verified");
        }

        Date expiry = claims.getExpirationTime();
        if (expiry == null || expiry.toInstant().isBefore(Instant.now())) {
            return new Result.Invalid(
                    "invalid_grant", "client_assertion is expired or has no exp claim");
        }

        if (claims.getAudience() == null || !claims.getAudience().contains(expectedAudience)) {
            return new Result.Invalid(
                    "invalid_grant", "client_assertion aud does not match this token endpoint");
        }

        String jti = claims.getJWTID();
        if (jti == null || !usedJtis.add(jti)) {
            return new Result.Invalid(
                    "invalid_grant", "client_assertion jti is missing or already used");
        }

        return new Result.Valid(issuer);
    }
}
