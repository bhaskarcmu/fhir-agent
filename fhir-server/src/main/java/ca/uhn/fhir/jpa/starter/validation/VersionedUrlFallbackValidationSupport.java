package ca.uhn.fhir.jpa.starter.validation;

import ca.uhn.fhir.context.FhirContext;
import ca.uhn.fhir.context.support.IValidationSupport;
import org.hl7.fhir.instance.model.api.IBaseResource;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Set;
import java.util.function.Function;

/**
 * Handles FHIR profile URLs with version suffixes (e.g., {@code Patient|4.0.1}) by
 * falling back to non-versioned URLs (e.g., {@code Patient}) when exact versioned
 * matches are not found in the validation chain.
 *
 * <p><b>Background:</b> When Implementation Guides reference FHIR base resources with
 * version suffixes (e.g., {@code http://hl7.org/fhir/StructureDefinition/Patient|4.0.1}),
 * validation fails with "Unable to locate profile" errors because HAPI FHIR's
 * {@link org.hl7.fhir.common.hapi.validation.support.DefaultProfileValidationSupport}
 * only loads profiles without version suffixes. The validation chain cannot match
 * the versioned canonical URL to any known StructureDefinition.
 *
 * <p><b>Workaround:</b> This support intercepts versioned canonical URLs, strips the
 * version suffix, and retries the lookup against the chain. It acts as a bridge between
 * IG-referenced versioned profiles and the core FHIR definitions loaded by
 * {@code DefaultProfileValidationSupport}.
 *
 * <p>For non-versioned URLs, or URLs not matching the configured prefixes, this support
 * returns {@code null} immediately, allowing other supports in the chain to handle them.
 *
 * <p><b>TODO:</b> HAPI FHIR should natively support versioned base profile resolution
 * or expose a hook for custom version-aware lookup. Track upstream progress at:
 * <a href="https://github.com/hapifhir/hapi-fhir/issues">https://github.com/hapifhir/hapi-fhir/issues</a>.
 * This class can be removed once HAPI FHIR handles versioned canonical URLs in
 * {@code DefaultProfileValidationSupport} without requiring a workaround.
 *
 * @see org.hl7.fhir.common.hapi.validation.support.DefaultProfileValidationSupport
 * @see org.hl7.fhir.common.hapi.validation.support.ValidationSupportChain
 */
public class VersionedUrlFallbackValidationSupport implements IValidationSupport {

	private static final Logger ourLog = LoggerFactory.getLogger(VersionedUrlFallbackValidationSupport.class);

	private final FhirContext myFhirContext;
	private final IValidationSupport myChain;
	private final Set<String> myUrlPrefixes;

	/**
	 * Creates a fallback validation support that only applies to URLs starting with the default prefix
	 * (http://hl7.org/fhir/StructureDefinition/).
	 */
	public VersionedUrlFallbackValidationSupport(FhirContext theFhirContext, IValidationSupport theChain) {
		this(theFhirContext, theChain, Set.of(URL_PREFIX_STRUCTURE_DEFINITION));
	}

	/**
	 * Creates a fallback validation support that only applies to URLs starting with the specified prefixes.
	 *
	 * @param theFhirContext the FHIR context
	 * @param theChain the validation support chain to delegate fallback lookups to
	 * @param theUrlPrefixes the URL prefixes to apply fallback logic to (e.g., "http://hl7.org/fhir/StructureDefinition/").
	 *                       Pass an empty set to apply to all URLs.
	 */
	public VersionedUrlFallbackValidationSupport(
			FhirContext theFhirContext, IValidationSupport theChain, Set<String> theUrlPrefixes) {
		myFhirContext = theFhirContext;
		myChain = theChain;
		myUrlPrefixes = theUrlPrefixes;
	}

	@Override
	public FhirContext getFhirContext() {
		return myFhirContext;
	}

	@Override
	public <T extends IBaseResource> T fetchResource(Class<T> theClass, String theUri) {
		return doFetchWithFallback(theUri, uri -> myChain.fetchResource(theClass, uri));
	}

	@Override
	public IBaseResource fetchStructureDefinition(String theUrl) {
		return doFetchWithFallback(theUrl, myChain::fetchStructureDefinition);
	}

	private <T extends IBaseResource> T doFetchWithFallback(String theUrl, Function<String, T> theFetcher) {
		// Check if this is a versioned URL (contains |)
		int pipeIndex = theUrl.indexOf('|');
		if (pipeIndex <= 0) {
			// Not a versioned URL, let other supports handle it
			return null;
		}

		String baseUrl = theUrl.substring(0, pipeIndex);

		// Check if this URL matches our configured prefixes
		if (!matchesPrefix(baseUrl)) {
			return null;
		}

		// Try exact versioned URL first
		T result = theFetcher.apply(theUrl);
		if (result != null) {
			return result;
		}

		// Try non-versioned URL fallback
		result = theFetcher.apply(baseUrl);
		if (result != null) {
			ourLog.warn(
					"Requested versioned canonical '{}' not found, falling back to non-versioned '{}'",
					theUrl,
					baseUrl);
			return result;
		}

		return null;
	}

	private boolean matchesPrefix(String theUrl) {
		if (myUrlPrefixes.isEmpty()) {
			return true;
		}
		for (String prefix : myUrlPrefixes) {
			if (theUrl.startsWith(prefix)) {
				return true;
			}
		}
		return false;
	}

	@Override
	public String getName() {
		return "VersionedUrlFallbackValidationSupport";
	}
}
