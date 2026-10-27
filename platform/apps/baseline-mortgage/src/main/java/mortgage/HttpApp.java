package mortgage;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.math.BigDecimal;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.Executors;

/**
 * HTTP front end. Requests are dispatched through {@link Routes#ALL} only. Each request is
 * checked for a live session, the idle limit that applies to its action and, where the route
 * requires it, step-up MFA. The service layer then applies the access matrix.
 */
public final class HttpApp {

    private static final int DEFAULT_TERM_YEARS = 30;
    private static final int MAX_BODY_BYTES = 64 * 1024;
    private static final int WORKER_THREADS = 2;

    private static final Map<String, Integer> STATUS_BY_CODE = Map.of(
            ServiceException.FORBIDDEN, 403,
            ServiceException.NOT_FOUND, 404,
            ServiceException.INVALID_STATE, 409,
            ServiceException.VALIDATION, 400,
            ServiceException.MAKER_CHECKER, 403,
            ServiceException.AUTHORITY, 403,
            ServiceException.DUPLICATE, 409);

    /** An incoming request. Header names are lower-case. */
    public record Request(String method, String path, String query, Map<String, String> headers, String body) {

        public static Request of(String method, String target, String token, String body) {
            int queryStart = target.indexOf('?');
            String path = queryStart < 0 ? target : target.substring(0, queryStart);
            String query = queryStart < 0 ? null : target.substring(queryStart + 1);
            Map<String, String> headers = new HashMap<>();
            if (token != null) {
                headers.put("authorization", "Bearer " + token);
            }
            return new Request(method, path, query, headers, body);
        }
    }

    /** A JSON response. */
    public record Response(int status, String body) {
    }

    private interface Handler {
        Object handle(Call call);
    }

    private record Call(Actor actor, Map<String, String> params, Map<String, String> query, Map<String, Object> body) {

        String param(String name) {
            return params.get(name);
        }

        String text(String name) {
            Object value = body.get(name);
            return value == null ? null : plain(value);
        }

        String requiredText(String name) {
            String value = text(name);
            if (value == null || value.isBlank()) {
                throw new ServiceException(ServiceException.VALIDATION, name + " is required");
            }
            return value;
        }

        BigDecimal amount(String name) {
            String value = text(name);
            return value == null ? null : new BigDecimal(value);
        }

        Map<String, String> stringMap(String name) {
            Map<String, String> fields = new LinkedHashMap<>();
            if (body.get(name) instanceof Map<?, ?> map) {
                for (Map.Entry<?, ?> entry : map.entrySet()) {
                    fields.put(String.valueOf(entry.getKey()), entry.getValue() == null ? null : plain(entry.getValue()));
                }
            }
            return fields;
        }

        private static String plain(Object value) {
            if (value instanceof BigDecimal decimal) {
                return decimal.toPlainString();
            }
            return String.valueOf(value);
        }
    }

    private final SessionStore sessions;
    private final CaseService cases;
    private final UserDirectory users;
    private final AppLog log;
    private final Map<String, Handler> handlers = new HashMap<>();

    public HttpApp(SessionStore sessions, CaseService cases, UserDirectory users, AppLog log) {
        this.sessions = sessions;
        this.cases = cases;
        this.users = users;
        this.log = log;
        bindHandlers();
        checkBindings();
    }

    public Response handle(Request request) {
        Optional<Routes.Match> match = Routes.find(request.method(), request.path());
        if (match.isEmpty()) {
            return unmatched(request);
        }
        Route route = match.get().route();
        if (route.isOpen()) {
            return invoke(route, null, match.get().params(), request);
        }
        Optional<Session> session = sessions.find(bearerToken(request));
        if (session.isEmpty()) {
            return error(401, "unauthenticated", "A valid session is required");
        }
        Optional<Response> refused = refuseSession(route, session.get());
        if (refused.isPresent()) {
            return refused.get();
        }
        session.get().touch();
        return invoke(route, session.get().actor(), match.get().params(), request);
    }

    public HttpServer start(InetSocketAddress address) throws IOException {
        HttpServer server = HttpServer.create(address, 0);
        server.createContext("/", this::serve);
        server.setExecutor(Executors.newFixedThreadPool(WORKER_THREADS, HttpApp::workerThread));
        server.start();
        return server;
    }

    /** Workers are daemons; the server's own dispatcher thread keeps the process alive. */
    private static Thread workerThread(Runnable task) {
        Thread thread = new Thread(task, "mortgage-http");
        thread.setDaemon(true);
        return thread;
    }

    private void bindHandlers() {
        handlers.put("GET /health", call -> Map.of("status", "ok"));
        handlers.put("GET /cases", call -> CaseViews.summaries(cases.list(call.actor())));
        handlers.put("POST /cases", this::createCase);
        handlers.put("GET /cases/{id}", call -> CaseViews.summary(cases.view(call.actor(), call.param("id"))));
        handlers.put("PUT /cases/{id}", this::editCase);
        handlers.put("GET /cases/{id}/npi", call -> cases.viewNpi(call.actor(), call.param("id")));
        handlers.put("POST /cases/{id}/submit", call -> CaseViews.summary(cases.submit(call.actor(), call.param("id"))));
        handlers.put("POST /cases/{id}/approve", call -> CaseViews.summary(cases.approve(call.actor(), call.param("id"))));
        handlers.put("POST /cases/{id}/decline", this::declineCase);
        handlers.put("POST /cases/{id}/override", this::overrideCase);
        handlers.put("POST /cases/{id}/withdraw", call -> CaseViews.summary(cases.withdraw(call.actor(), call.param("id"))));
        handlers.put("POST /cases/{id}/close", call -> CaseViews.summary(cases.close(call.actor(), call.param("id"))));
        handlers.put("POST /cases/{id}/legal-hold", this::setLegalHold);
        handlers.put("GET /cases/{id}/notes", call -> CaseViews.notes(cases.notes(call.actor(), call.param("id"))));
        handlers.put("POST /cases/{id}/notes", this::addNote);
        handlers.put("GET /cases/{id}/checklist", call -> CaseViews.checklist(cases.checklist(call.actor(), call.param("id"))));
        handlers.put("POST /cases/{id}/documents/{document}", this::receiveDocument);
        handlers.put("POST /cases/{id}/quote", this::quote);
        handlers.put("GET /reports/pipeline", call -> CaseViews.pipeline(cases.pipeline(call.actor())));
        handlers.put("GET /exports/cases", call -> cases.export(call.actor()));
        handlers.put("POST /admin/users", this::assignRole);
        handlers.put("GET /audit", call -> CaseViews.auditEvents(cases.auditTrail(call.actor(), call.query().get("target"))));
        handlers.put("POST /admin/retention/purge", call -> Map.of("purged", cases.purgeExpiredNpi(call.actor())));
    }

    /** Every route must have a handler and every handler must belong to a route. */
    private void checkBindings() {
        Set<String> routeKeys = new HashSet<>();
        for (Route route : Routes.ALL) {
            routeKeys.add(route.key());
            if (!handlers.containsKey(route.key())) {
                throw new IllegalStateException("No handler for route " + route.key());
            }
        }
        for (String key : handlers.keySet()) {
            if (!routeKeys.contains(key)) {
                throw new IllegalStateException("Handler has no route: " + key);
            }
        }
    }

    private static Optional<Response> refuseSession(Route route, Session session) {
        if (session.isIdleExpired(route.action().isPrivileged())) {
            return Optional.of(error(401, "session_expired", "The session has been idle too long"));
        }
        if (route.mfaRequired() && !session.mfaVerified()) {
            return Optional.of(error(403, "mfa_required", "Step-up MFA is required"));
        }
        return Optional.empty();
    }

    private Response invoke(Route route, Actor actor, Map<String, String> params, Request request) {
        try {
            Call call = new Call(actor, params, parseQuery(request.query()), Json.parseObject(request.body()));
            Object result = handlers.get(route.key()).handle(call);
            return new Response(200, Json.write(result));
        } catch (ServiceException e) {
            return error(STATUS_BY_CODE.getOrDefault(e.code(), 400), e.code(), e.getMessage());
        } catch (IllegalArgumentException | ArithmeticException e) {
            return error(400, "bad_request", "The request could not be read");
        } catch (RuntimeException e) {
            log.error("Unhandled " + e.getClass().getSimpleName() + " on " + route.key());
            return error(500, "internal_error", "Unexpected error");
        }
    }

    private Object createCase(Call call) {
        LoanCase created = cases.create(call.actor(), call.stringMap("applicant"), loanRequest(call));
        return CaseViews.summary(created);
    }

    private Object editCase(Call call) {
        LoanCase edited = cases.edit(call.actor(), call.param("id"), call.stringMap("applicant"), loanRequest(call));
        return CaseViews.summary(edited);
    }

    private Object declineCase(Call call) {
        LoanCase declined = cases.decline(call.actor(), call.param("id"), call.text("reason"));
        return CaseViews.summary(declined);
    }

    private Object overrideCase(Call call) {
        LoanCase overridden = cases.override(call.actor(), call.param("id"), call.requiredText("justification"));
        return CaseViews.summary(overridden);
    }

    private Object setLegalHold(Call call) {
        boolean hold = Boolean.TRUE.equals(call.body().get("hold"));
        return CaseViews.summary(cases.setLegalHold(call.actor(), call.param("id"), hold));
    }

    private Object addNote(Call call) {
        CaseNote note = cases.addNote(call.actor(), call.param("id"), call.requiredText("text"));
        return CaseViews.note(note);
    }

    private Object receiveDocument(Call call) {
        DocumentType document = DocumentType.valueOf(call.param("document").toUpperCase(Locale.ROOT));
        return CaseViews.checklist(cases.markDocumentReceived(call.actor(), call.param("id"), document));
    }

    private Object quote(Call call) {
        BigDecimal term = call.amount("term_years");
        int termYears = term == null ? DEFAULT_TERM_YEARS : term.intValueExact();
        return CaseViews.quote(cases.quote(call.actor(), call.param("id"), termYears));
    }

    private Object assignRole(Call call) {
        String userId = call.requiredText("user_id");
        Role role = Role.valueOf(call.requiredText("role"));
        users.assignRole(call.actor(), userId, role);
        return Map.of("user_id", userId, "role", role.name());
    }

    private static LoanRequest loanRequest(Call call) {
        return new LoanRequest(call.amount("loan_amount"), call.amount("appraised_value"), call.amount("monthly_debt"));
    }

    private static Response unmatched(Request request) {
        if (Routes.pathExists(request.path())) {
            return error(405, "method_not_allowed", "Method not allowed");
        }
        return error(404, "not_found", "No such route");
    }

    private static String bearerToken(Request request) {
        String header = request.headers().get("authorization");
        if (header == null || !header.startsWith("Bearer ")) {
            return null;
        }
        return header.substring("Bearer ".length());
    }

    private static Map<String, String> parseQuery(String query) {
        Map<String, String> values = new HashMap<>();
        if (query == null || query.isEmpty()) {
            return values;
        }
        for (String pair : query.split("&")) {
            int split = pair.indexOf('=');
            String name = split < 0 ? pair : pair.substring(0, split);
            String value = split < 0 ? "" : pair.substring(split + 1);
            values.put(decode(name), decode(value));
        }
        return values;
    }

    private static String decode(String value) {
        return URLDecoder.decode(value, StandardCharsets.UTF_8);
    }

    private static Response error(int status, String code, String message) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("error", code);
        body.put("message", message);
        return new Response(status, Json.write(body));
    }

    private void serve(HttpExchange exchange) throws IOException {
        try {
            Response response = handle(toRequest(exchange));
            byte[] body = response.body().getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type", "application/json");
            exchange.sendResponseHeaders(response.status(), body.length);
            exchange.getResponseBody().write(body);
        } finally {
            exchange.close();
        }
    }

    private static Request toRequest(HttpExchange exchange) throws IOException {
        Map<String, String> headers = new HashMap<>();
        for (Map.Entry<String, List<String>> header : exchange.getRequestHeaders().entrySet()) {
            if (!header.getValue().isEmpty()) {
                headers.put(header.getKey().toLowerCase(Locale.ROOT), header.getValue().get(0));
            }
        }
        String body = new String(exchange.getRequestBody().readNBytes(MAX_BODY_BYTES), StandardCharsets.UTF_8);
        URI uri = exchange.getRequestURI();
        return new Request(exchange.getRequestMethod(), uri.getPath(), uri.getRawQuery(), headers, body);
    }
}
