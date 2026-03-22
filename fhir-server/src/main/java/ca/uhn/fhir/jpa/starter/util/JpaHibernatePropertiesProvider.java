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

	public JpaHibernatePropertiesProvider(
			LocalContainerEntityManagerFactoryBean theEntityManagerFactory,
			Environment theEnvironment) {
		// Check the JPA property map first (set after full initialisation).
		// Fall back to spring.jpa.properties.hibernate.dialect from the Spring
		// Environment — this is reliably available even before the entity manager
		// factory bean is fully initialised, which prevents dialect auto-detection
		// from opening a connection to a fallback embedded H2 datasource.
		String dialectClass =
				(String) theEntityManagerFactory.getJpaPropertyMap().get("hibernate.dialect");
		if (!isNotBlank(dialectClass)) {
			dialectClass = theEnvironment.getProperty("spring.jpa.properties.hibernate.dialect");
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
