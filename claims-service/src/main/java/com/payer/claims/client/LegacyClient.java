package com.payer.claims.client;

/** Transport to the legacy core (rxclaim-emulator). Sends/receives raw fixed-width records;
 *  translation to/from canonical form is the ACL's job, not the client's. */
public interface LegacyClient {
    String send(String legacyClaimRecord);
}
