package mortgage;

import java.util.List;
import java.util.Map;
import java.util.Optional;

/** The route table. HttpApp serves these routes and nothing else. */
public final class Routes {

    public static final List<Route> ALL = List.of(
            Route.open("GET", "/health"),
            new Route("GET", "/cases", Action.VIEW_CASE, false),
            new Route("POST", "/cases", Action.CREATE_CASE, false),
            new Route("GET", "/cases/{id}", Action.VIEW_CASE, false),
            new Route("PUT", "/cases/{id}", Action.EDIT_CASE, false),
            new Route("GET", "/cases/{id}/npi", Action.VIEW_NPI, true),
            new Route("POST", "/cases/{id}/submit", Action.SUBMIT_CASE, false),
            new Route("POST", "/cases/{id}/approve", Action.APPROVE_CREDIT, true),
            new Route("POST", "/cases/{id}/decline", Action.DECLINE_CREDIT, false),
            new Route("POST", "/cases/{id}/override", Action.OVERRIDE_POLICY, true),
            new Route("POST", "/cases/{id}/withdraw", Action.EDIT_CASE, false),
            new Route("POST", "/cases/{id}/close", Action.EDIT_CASE, false),
            new Route("POST", "/cases/{id}/legal-hold", Action.PURGE_NPI, true),
            new Route("GET", "/cases/{id}/notes", Action.VIEW_CASE, false),
            new Route("POST", "/cases/{id}/notes", Action.EDIT_CASE, false),
            new Route("GET", "/cases/{id}/checklist", Action.VIEW_CASE, false),
            new Route("POST", "/cases/{id}/documents/{document}", Action.EDIT_CASE, false),
            new Route("POST", "/cases/{id}/quote", Action.EDIT_CASE, false),
            new Route("GET", "/reports/pipeline", Action.VIEW_CASE, false),
            new Route("GET", "/exports/cases", Action.EXPORT_CASES, true),
            new Route("POST", "/admin/users", Action.MANAGE_USERS, true),
            new Route("GET", "/audit", Action.VIEW_AUDIT, false),
            new Route("POST", "/admin/retention/purge", Action.PURGE_NPI, true)
    );

    private Routes() {
    }

    /** A route together with the parameters taken from the request path. */
    public record Match(Route route, Map<String, String> params) {
    }

    public static Optional<Match> find(String method, String path) {
        for (Route route : ALL) {
            Optional<Map<String, String>> params = route.matchPath(path);
            if (route.method().equals(method) && params.isPresent()) {
                return Optional.of(new Match(route, params.get()));
            }
        }
        return Optional.empty();
    }

    public static boolean pathExists(String path) {
        for (Route route : ALL) {
            if (route.matchPath(path).isPresent()) {
                return true;
            }
        }
        return false;
    }
}
