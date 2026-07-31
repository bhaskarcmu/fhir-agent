package com.healthcare.epic.auth;

import com.healthcare.epic.quirks.EpicOperationOutcome;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * Gates every proxied FHIR call behind a valid bearer token (PRD FR2/FR8). Missing or invalid
 * tokens get Epic's {@code OperationOutcome} error shape (quirk C, design.md &sect;6/&sect;14) —
 * this was deliberately deferred from M2 to here rather than dropped; M2's own definition of done
 * only required rejection, not a specific error body.
 */
@Component
@Order(1)
public class BearerAuthFilter extends OncePerRequestFilter {

    private final AccessTokenStore tokenStore;

    public BearerAuthFilter(AccessTokenStore tokenStore) {
        this.tokenStore = tokenStore;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getRequestURI();
        return path.equals("/oauth2/token") || path.startsWith("/actuator/");
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        String header = request.getHeader("Authorization");
        String token =
                (header != null && header.startsWith("Bearer "))
                        ? header.substring("Bearer ".length())
                        : null;

        if (token == null || tokenStore.validate(token).isEmpty()) {
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setHeader("WWW-Authenticate", "Bearer error=\"invalid_token\"");
            response.setContentType("application/fhir+json");
            response
                    .getOutputStream()
                    .write(
                            EpicOperationOutcome.json(
                                    "invalid-token", "Missing, invalid, or expired bearer token"));
            return;
        }

        chain.doFilter(request, response);
    }
}
