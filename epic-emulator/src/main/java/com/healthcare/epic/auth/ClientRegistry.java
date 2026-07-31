package com.healthcare.epic.auth;

import com.nimbusds.jose.jwk.RSAKey;
import java.text.ParseException;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Component;

/**
 * In-memory registry of clients registered per {@link AuthProperties}: client id &rarr; its
 * public RSA key. Only the public half is ever held here — the matching private key stays with
 * whoever is acting as the client, exactly as SMART Backend Services' asymmetric registration
 * model intends.
 */
@Component
public class ClientRegistry {

    private final Map<String, RSAKey> byClientId = new HashMap<>();

    public ClientRegistry(AuthProperties properties) {
        for (AuthProperties.ClientConfig client : properties.getClients()) {
            try {
                byClientId.put(client.getClientId(), RSAKey.parse(client.getJwk()));
            } catch (ParseException e) {
                throw new IllegalStateException(
                        "Malformed JWK for registered client '" + client.getClientId() + "'", e);
            }
        }
    }

    public Optional<RSAKey> find(String clientId) {
        return Optional.ofNullable(byClientId.get(clientId));
    }
}
