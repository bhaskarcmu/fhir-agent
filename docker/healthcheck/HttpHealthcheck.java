import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public class HttpHealthcheck {
    public static void main(String[] args) throws Exception {
        String url = args.length > 0 ? args[0] : "http://localhost:8080/fhir/metadata";
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .build();
        HttpRequest request = HttpRequest.newBuilder(URI.create(url))
                .timeout(Duration.ofSeconds(8))
                .header("Accept", "application/fhir+json")
                .GET()
                .build();

        int statusCode = client.send(request, HttpResponse.BodyHandlers.discarding()).statusCode();
        if (statusCode < 200 || statusCode >= 300) {
            System.err.println("Healthcheck failed: HTTP " + statusCode + " from " + url);
            System.exit(1);
        }
    }
}
