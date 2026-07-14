package com.payer.claims.kb;

import com.payer.claims.domain.FormularyEntry;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/**
 * File-backed {@link PayerKb} — loads {@code formulary.csv} from the payer knowledge base
 * (data/payer-kb) into an in-memory map keyed by {@code planId|rxcui}. The curated fixtures are
 * small (R13); at scale this same interface is served from a KV store (C3).
 */
@Component
public class FilePayerKb implements PayerKb {

    private final Map<String, FormularyEntry> byKey = new HashMap<>();

    @Autowired
    public FilePayerKb(@Value("${payer-kb.dir:../data/payer-kb}") String dir) {
        this(Path.of(dir));
    }

    /** Testable constructor: load from an explicit payer-kb directory. */
    public FilePayerKb(Path dir) {
        Path csv = dir.resolve("formulary/formulary.csv");
        try {
            List<String> lines = Files.readAllLines(csv);
            for (int i = 1; i < lines.size(); i++) { // skip header
                String line = lines.get(i).strip();
                if (line.isEmpty()) continue;
                FormularyEntry e = parse(line);
                byKey.put(key(e.planId(), e.rxcui()), e);
            }
        } catch (IOException ex) {
            throw new UncheckedIOException("Cannot load payer KB formulary from " + csv, ex);
        }
    }

    @Override
    public Optional<FormularyEntry> formularyEntry(String planId, String rxcui) {
        return Optional.ofNullable(byKey.get(key(planId, rxcui)));
    }

    private static FormularyEntry parse(String line) {
        // plan_id,rxcui,drug,tier,prior_auth,step_therapy,quantity_limit,quantity_limit_qty,covered
        String[] c = line.split(",", -1);
        return new FormularyEntry(
                c[0].trim(), c[1].trim(), c[2].trim(), c[3].trim(),
                Boolean.parseBoolean(c[4].trim()),
                Boolean.parseBoolean(c[5].trim()),
                Boolean.parseBoolean(c[6].trim()),
                leadingInt(c[7].trim()),
                Boolean.parseBoolean(c[8].trim()));
    }

    /** Extract the leading integer of a quantity-limit string ("30/30d" -> 30; "" -> null). */
    public static Integer leadingInt(String s) {
        int i = 0;
        while (i < s.length() && Character.isDigit(s.charAt(i))) i++;
        return i == 0 ? null : Integer.valueOf(s.substring(0, i));
    }

    private static String key(String planId, String rxcui) {
        return planId + "|" + rxcui;
    }
}
