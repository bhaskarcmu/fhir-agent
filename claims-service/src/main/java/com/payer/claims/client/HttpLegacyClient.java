package com.payer.claims.client;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

/**
 * HTTP transport to the internal rxclaim-emulator. The emulator is never on the edge gateway;
 * in cloud this base URL is its internal Cloud Run address.
 */
@Component
public class HttpLegacyClient implements LegacyClient {

    private final RestClient http;

    public HttpLegacyClient(@Value("${rxclaim.base-url:http://localhost:8091}") String baseUrl) {
        this.http = RestClient.builder().baseUrl(baseUrl).build();
    }

    @Override
    public String send(String legacyClaimRecord) {
        return http.post()
                .uri("/rxclaim/adjudicate")
                .contentType(MediaType.TEXT_PLAIN)
                .accept(MediaType.TEXT_PLAIN)
                .body(legacyClaimRecord)
                .retrieve()
                .body(String.class);
    }
}
