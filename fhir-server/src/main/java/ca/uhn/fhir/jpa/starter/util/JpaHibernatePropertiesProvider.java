package ca.uhn.fhir.jpa.starter.util;

import ca.uhn.fhir.context.ConfigurationException;
import ca.uhn.fhir.jpa.config.HibernatePropertiesProvider;
import ca.uhn.fhir.util.ReflectionUtil;
import org.hibernate.dialect.Dialect;
import org.hibernate.engine.jdbc.dialect.internal.StandardDialectResolver;
import org.hibernate.engine.jdbc.dialect.spi.DatabaseMetaDataDialectResolutionInfoAdapter;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.core.env.Environment;
import org.springframework.orm.jpa.LocalContainerEntityManagerFactoryBean;

import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

import static org.apache.commons.lang3.StringUtils.isNotBlank;

public class JpaHibernatePropertiesProvider extends HibernatePropertiesProvider {
	private static final Logger ourLog = LoggerFactory.getLogger(JpaHibernatePropertiesProvider.class);

	private final Dialect myDialect;

	/**
	 * Resolves the Hibernate dialect using an explicit priority order to prevent
	 * unwanted JDBC-based auto-detection in multi-datasource environments.
	 *
	 * <p><b>Why this matters:</b> In environments where Neon (PostgreSQL) env vars are
	 * set globally (e.g., {@code SPRING_DATASOURCE_DRIVER_CLASS_NAME=org.postgresql.Driver}),
	 * the default HAPI FHIR dialect resolution opens a JDBC connection to determine the
	 * dialect. If the target database is H2 (e.g., during testing), the Postgres driver
	 * rejects the H2 URL, causing startup failure.
	 *
	 * <p><b>Priority order:</b>
	 * <ol>
	 *   <li>{@code spring.jpa.properties.hibernate.dialect} from Spring {@link Environment}
	 *       — most reliable; available before the entity manager factory is fully initialised,
	 *       and takes precedence over environment variables when set in {@code @SpringBootTest}
	 *       properties.</li>
	 *   <li>{@code hibernate.dialect} from the JPA property map — set after full
	 *       initialisation; used when the dialect is configured via {@code spring.jpa.properties}
	 *       in YAML rather than as an env var.</li>
	 *   <li>JDBC connection-based auto-detection — last resort; opens a real database
	 *       connection. Avoided when possible because it can select the wrong driver in
	 *       mixed-datasource environments.</li>
	 * </ol>
	 *
	 * @param theEntityManagerFactory the JPA entity manager factory bean
	 * @param theEnvironment          the Spring environment (used for property lookup)
	 * @see ca.uhn.fhir.jpa.config.HibernatePropertiesProvider
	 */
	public JpaHibernatePropertiesProvider(
			LocalContainerEntityManagerFactoryBean theEntityManagerFactory,
			Environment theEnvironment) {
		// Priority 1: Spring Environment property (highest reliability; wins over env vars
		// when overridden in @SpringBootTest properties, which is critical for H2 tests
		// running in an environment that also has Neon env vars set globally).
		String dialectClass = theEnvironment.getProperty("spring.jpa.properties.hibernate.dialect");
		if (!isNotBlank(dialectClass)) {
			// Priority 2: JPA property map (populated after full bean initialisation).
			dialectClass = (String) theEntityManagerFactory.getJpaPropertyMap().get("hibernate.dialect");
		}
		if (isNotBlank(dialectClass)) {
			myDialect = ReflectionUtil.newInstanceOrReturnNull(dialectClass, Dialect.class);
		} else {
			ourLog.warn(
					"'hibernate.dialect' not set in application configuration! Please explicitly specify a valid HAPI FHIR hibernate dialect.");
			DataSource connection = theEntityManagerFactory.getDataSource();
			try (Connection dbConnection = connection.getConnection()) {
				myDialect = new StandardDialectResolver()
						.resolveDialect(new DatabaseMetaDataDialectResolutionInfoAdapter(dbConnection.getMetaData()));
			} catch (SQLException sqlException) {
				throw new ConfigurationException(sqlException.getMessage(), sqlException);
			}
		}
	}

	@Override
	public Dialect getDialect() {
		return myDialect;
	}
}
