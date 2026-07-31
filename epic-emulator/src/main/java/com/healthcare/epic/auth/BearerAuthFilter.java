package com.healthcare.epic.auth;

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
 * tokens get a plain OAuth2-style 401 — not yet Epic's {@code OperationOutcome} shape. That
 * upgrade is FR6/quirk C, scoped to M4; M2's own definition of done (design.md &sect;12) only
 * requires rejection, not a specific error body, so this is a deliberate sequencing choice, not
 * a dropped requirement.
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
            response.setContentType("application/json");
            response.getWriter().write("{\"error\":\"invalid_token\"}");
            return;
        }

        chain.doFilter(request, response);
    }
}
