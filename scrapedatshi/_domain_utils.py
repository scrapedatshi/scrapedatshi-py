"""
scrapedatshi._domain_utils
~~~~~~~~~~~~~~~~~~~~~~~~~~
Domain scope validation for local-fetch crawl mode.

Used to determine whether a target URL falls within the permitted security
scope of the root domain — preventing cookie/header leakage to external
domains during local BFS crawls.

The ``_is_matching_domain_scope()`` function is the single source of truth
for both the BFS queue filter and the credential-passing shield.  Both must
use the same logic to guarantee operational symmetry.

Multi-part TLD safety:
    The naive ``parts[-2:]`` split approach fails for domains like
    ``wiki.company.co.uk`` — it would extract ``co.uk`` as the apex domain,
    causing cookie leakage to any other ``.co.uk`` site.  This module uses
    a heuristic that detects common registry-level second-level domains
    (co, com, org, net, edu, gov, ac) and adjusts the apex length to 3
    segments instead of 2.
"""

from __future__ import annotations

from urllib.parse import urlparse

# Common registry-level second-level domain labels that appear before the TLD.
# When the second-to-last segment of a domain matches one of these, the apex
# domain requires 3 segments (e.g. company.co.uk) rather than 2 (company.com).
_COMMON_REGISTRY_PREFIXES: frozenset[str] = frozenset(
    ("co", "com", "org", "net", "edu", "gov", "ac")
)


def _is_matching_domain_scope(
    target_url: str,
    root_url: str,
    allow_subdomains: bool = False,
) -> bool:
    """
    Returns True if ``target_url`` falls within the permitted security scope
    of ``root_url``.

    Security model:
        - **Exact match** (default): only the exact same hostname is permitted.
          This is the safest default and prevents all cross-domain leakage.
        - **Subdomain scope** (``allow_subdomains=True``): permits subdomains
          of the root domain and horizontal sibling subdomains sharing the
          same apex domain.  Multi-part TLDs (.co.uk, .com.br, etc.) are
          handled correctly via the registry-prefix heuristic.

    Args:
        target_url:       The URL being evaluated (e.g. a discovered link).
        root_url:         The seed URL that started the crawl.
        allow_subdomains: If True, permits subdomains of the root domain.
                          Defaults to False (exact match only).

    Returns:
        True if the target is within scope; False otherwise.

    Examples::

        # Exact match — always True
        _is_matching_domain_scope("https://company.com/page", "https://company.com") → True

        # Subdomain — False by default, True with allow_subdomains=True
        _is_matching_domain_scope("https://wiki.company.com", "https://company.com") → False
        _is_matching_domain_scope("https://wiki.company.com", "https://company.com",
                                   allow_subdomains=True) → True

        # Multi-part TLD — safe with allow_subdomains=True
        _is_matching_domain_scope("https://wiki.company.co.uk", "https://company.co.uk",
                                   allow_subdomains=True) → True

        # External domain — always False
        _is_matching_domain_scope("https://evil.co.uk", "https://company.co.uk",
                                   allow_subdomains=True) → False
    """
    root_netloc = urlparse(root_url).netloc.lower()
    target_netloc = urlparse(target_url).netloc.lower()

    # Strip port numbers if present (e.g. company.com:8080 → company.com)
    root_netloc = root_netloc.split(":")[0]
    target_netloc = target_netloc.split(":")[0]

    # 1. Exact match — always safe, no further checks needed
    if root_netloc == target_netloc:
        return True

    # 2. Opt-in subdomain scope evaluation
    if allow_subdomains:
        # Path A: Downward match — root is the apex, target is a subdomain
        # e.g. root=company.com, target=wiki.company.com
        if target_netloc.endswith("." + root_netloc):
            return True

        # Path B: Horizontal match — both are subdomains of the same apex
        # e.g. root=wiki.company.com, target=docs.company.com
        root_parts = root_netloc.split(".")
        target_parts = target_netloc.split(".")

        # Heuristic: detect multi-part TLDs by checking the second-to-last
        # segment against known registry-level prefixes.
        # e.g. company.co.uk → root_parts[-2] = "co" → apex_len = 3
        # e.g. company.com   → root_parts[-2] = "company" → apex_len = 2
        if len(root_parts) >= 3 and root_parts[-2] in _COMMON_REGISTRY_PREFIXES:
            apex_len = 3
        else:
            apex_len = 2

        if len(root_parts) >= apex_len and len(target_parts) >= apex_len:
            root_apex = ".".join(root_parts[-apex_len:])
            target_apex = ".".join(target_parts[-apex_len:])
            if root_apex == target_apex:
                return True

    return False
