package com.payer.claims;

import static org.assertj.core.api.Assertions.assertThat;

import com.payer.claims.domain.FormularyEntry;
import com.payer.claims.kb.FilePayerKb;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class FilePayerKbTest {

    @Test
    void loadsFormularyAndLooksUpByPlanAndRxcui(@TempDir Path dir) throws IOException {
        Path csv = dir.resolve("formulary/formulary.csv");
        Files.createDirectories(csv.getParent());
        Files.writeString(csv, """
                plan_id,rxcui,drug,tier,prior_auth,step_therapy,quantity_limit,quantity_limit_qty,covered
                COM-SILVER,1991302,semaglutide,SPECIALTY,true,false,true,4pens/28d,true
                EMP-PPO,1991302,semaglutide,NON-FORMULARY,false,false,true,4pens/28d,false
                """);

        FilePayerKb kb = new FilePayerKb(dir);

        Optional<FormularyEntry> silver = kb.formularyEntry("COM-SILVER", "1991302");
        assertThat(silver).isPresent();
        assertThat(silver.get().priorAuth()).isTrue();
        assertThat(silver.get().quantityLimit()).isTrue();
        assertThat(silver.get().quantityLimitQty()).isEqualTo(4);   // parsed leading int of "4pens/28d"
        assertThat(silver.get().covered()).isTrue();

        assertThat(kb.formularyEntry("EMP-PPO", "1991302").get().covered()).isFalse();
        assertThat(kb.formularyEntry("COM-GOLD", "1991302")).isEmpty();
    }

    @Test
    void leadingIntParsesQuantityLimitStrings() {
        assertThat(FilePayerKb.leadingInt("30/30d")).isEqualTo(30);
        assertThat(FilePayerKb.leadingInt("4pens/28d")).isEqualTo(4);
        assertThat(FilePayerKb.leadingInt("")).isNull();
    }
}
