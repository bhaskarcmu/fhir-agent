package com.healthcare.epic.auth;

import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * The SMART Backend Services token endpoint (PRD FR2): a registered client presents a signed JWT
 * client assertion and, if it validates, receives a short-lived opaque bearer token.
 *
 * <p>More specific than {@code proxy.FhirProxyController}'s catch-all {@code /**} mapping, so
 * Spring routes {@code /oauth2/token} here rather than forwarding it upstream — no explicit
 * exclusion needed, same reasoning as the actuator endpoints in M1.
 */
@RestController
public class TokenController {

    private static final String JWT_BEARER_ASSERTION_TYPE =
            "urn:ietf:params:oauth:client-assertion-type:jwt-bearer";

    private final ClientAssertionValidator validator;
    private final AccessTokenStore tokenStore;

    public TokenController(ClientAssertionValidator validator, AccessTokenStore tokenStore) {
        this.validator = validator;
        this.tokenStore = tokenStore;
    }

    @PostMapping(value = "/oauth2/token", consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<Map<String, Object>> token(
            @RequestParam("grant_type") String grantType,
            @RequestParam(value = "client_assertion_type", required = false) String assertionType,
            @RequestParam(value = "client_assertion", required = false) String clientAssertion,
            @RequestParam(value = "scope", required = false) String scope) {

        if (!"client_credentials".equals(grantType)) {
            return oauthError(
                    HttpStatus.BAD_REQUEST,
                    "unsupported_grant_type",
                    "grant_type must be client_credentials");
        }
        if (!JWT_BEARER_ASSERTION_TYPE.equals(assertionType) || clientAssertion == null) {
            return oauthError(
                    HttpStatus.BAD_REQUEST,
                    "invalid_request",
                    "client_assertion_type must be "
                            + JWT_BEARER_ASSERTION_TYPE
                            + " and client_assertion must be present");
        }

        ClientAssertionValidator.Result result = validator.validate(clientAssertion);
        if (result instanceof ClientAssertionValidator.Result.Invalid invalid) {
            return oauthError(HttpStatus.BAD_REQUEST, invalid.error(), invalid.errorDescription());
        }

        String clientId = ((ClientAssertionValidator.Result.Valid) result).clientId();
        String accessToken = tokenStore.issue(clientId);

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("access_token", accessToken);
        body.put("token_type", "bearer");
        body.put("expires_in", tokenStore.ttlSeconds());
        if (scope != null) {
            body.put("scope", scope);
        }
        return ResponseEntity.ok(body);
    }

    private ResponseEntity<Map<String, Object>> oauthError(
            HttpStatus status, String error, String description) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("error", error);
        body.put("error_description", description);
        return ResponseEntity.status(status).body(body);
    }
}
