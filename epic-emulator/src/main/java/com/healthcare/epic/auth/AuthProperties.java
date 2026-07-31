package com.healthcare.epic.auth;

import java.util.ArrayList;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * Dev-simple client registration (design.md &sect;4/&sect;14, decision E8): a client's public key
 * is registered via config, not a real vendor approval workflow. Add a client by adding an entry
 * under {@code epic.auth.clients} in {@code application.yml} (or as a test property) — no UI, no
 * restart-free registration endpoint, matching the "keep developer access simple" instruction.
 */
@Component
@ConfigurationProperties(prefix = "epic.auth")
public class AuthProperties {

    /** Expected {@code aud} claim on the client assertion JWT — this token endpoint's own URL. */
    private String tokenEndpoint = "http://localhost:8092/oauth2/token";

    /** How long an issued access token remains valid. */
    private long tokenTtlSeconds = 300;

    private List<ClientConfig> clients = new ArrayList<>();

    public String getTokenEndpoint() {
        return tokenEndpoint;
    }

    public void setTokenEndpoint(String tokenEndpoint) {
        this.tokenEndpoint = tokenEndpoint;
    }

    public long getTokenTtlSeconds() {
        return tokenTtlSeconds;
    }

    public void setTokenTtlSeconds(long tokenTtlSeconds) {
        this.tokenTtlSeconds = tokenTtlSeconds;
    }

    public List<ClientConfig> getClients() {
        return clients;
    }

    public void setClients(List<ClientConfig> clients) {
        this.clients = clients;
    }

    /** One registered test client: its id, and its public key as a JWK JSON string. */
    public static class ClientConfig {
        private String clientId;
        private String jwk;

        public String getClientId() {
            return clientId;
        }

        public void setClientId(String clientId) {
            this.clientId = clientId;
        }

        public String getJwk() {
            return jwk;
        }

        public void setJwk(String jwk) {
            this.jwk = jwk;
        }
    }
}
