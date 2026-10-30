BASE_HEADERS = {
    "accept": "*/*",
    "accept-language": "en-US,en;q=0.9",
    "access-control-allow-headers": "sentry-trace, baggage",
    "apollo-require-preflight": "true",
    "apollographql-client-name": "web",
    "content-type": "application/json",
    "origin": "https://playerok.com",
    "priority": "u=1, i",
    "referer": "https://playerok.com/",
    "sec-ch-ua": '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "x-gql-op": "viewer",
    "x-gql-path": "/products/[slug]",
    "x-timezone-offset": "-180",
}

EXAMPLE_USER_AGENTS = [
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/143.0.7499.41 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/143.0.7499.110 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/143.0.7499.169 Safari/537.36"
    ),
]

CLOUDFLARE_SIGNATURES = [
    "<title>Just a moment...</title>",
    "window._cf_chl_opt",
    "Enable JavaScript and cookies to continue",
    "Checking your browser before accessing",
    "cf-browser-verification",
    "Cloudflare Ray ID",
]
