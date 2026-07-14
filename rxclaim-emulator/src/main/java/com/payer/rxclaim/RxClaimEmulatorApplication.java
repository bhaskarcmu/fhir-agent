package com.payer.rxclaim;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * Simulated legacy IBM i / RxClaim adjudication core (Phase 2, M2).
 *
 * <p>This service stands in for the legacy RxClaim engine that historically runs on IBM i
 * (Db2 for i, RPG/CL). In the modernization "strangler snapshot" it still owns the member
 * system-of-record, drug pricing, and accumulators; the modern claims-service wraps it behind
 * a fa&ccedil;ade + anti-corruption layer and never lets consumers call it directly.
 *
 * <p>It speaks a deliberately legacy contract: fixed-width (DDS-style) request/response
 * records over a REST fa&ccedil;ade, backed by DB2/SQL400-style tables. It is internal-only
 * (no edge gateway route; Cloud Run {@code ingress=internal} in cloud).
 */
@SpringBootApplication
public class RxClaimEmulatorApplication {
    public static void main(String[] args) {
        SpringApplication.run(RxClaimEmulatorApplication.class, args);
    }
}
