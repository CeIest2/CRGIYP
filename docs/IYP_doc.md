# IYP (Internet Yellow Pages) — Graph Schema & Agent Reference
**Master v3.3**

> **Role:** Absolute reference for the IYP/YPI Knowledge Graph structure, node labels, relationship types, and property names.
> **Usage:** The Agent MUST use this topology to navigate the graph and formulate Cypher queries. ONLY use the Corrected Keys listed below. **DO NOT invent or guess properties.**

---

## 1. 🚨 CRITICAL QUERY RULES FOR THE AGENT 🚨

- **Do not guess keys** — Always check the "Corrected Keys" in Section 3.
  - Example: For market share (APNIC), use `r.percent`, **NEVER** `population_percent`.

- **Data Types & Identifiers:**
  - `asn` is **ALWAYS** an Integer (e.g., `2497`, not `"AS2497"`).
  - `country_code` is **ALWAYS** ISO-2 String (e.g., `'FR'`, `'JP'`).
  - `af` (Address Family) is **ALWAYS** an Integer (`4` or `6`).

- **Retrieving ONE Descriptive Name (e.g., AS Name):** If you need to attach a single descriptive name to a node to avoid Cartesian products, you MAY use `COLLECT(n.name)[0]`. 
- 🚨 **PROHIBITED ANTI-PATTERN:** NEVER use `COLLECT(x)[0]` when the user asks for a LIST of distinct entities (e.g., "Top 1000 domain names", "All prefixes"). If the goal is to return multiple different items, use standard `WITH DISTINCT x` or `RETURN DISTINCT x`.

---

## 2. NODE TYPES & IDENTIFIERS

| Node Type | Description & Primary Keys (PK) |
|---|---|
| `:AS` | Autonomous System. PK: `.asn` (Integer). Identifiers: `.org_name`, `.website`, `.irr_status`, `.is_public`, `.country_code`, `.created`. Classification: `.tags_0_name` to `.tags_5_name`, `.info_type`, `.info_scope`. Physical: `.ix_count`, `.fac_count`, `.net_count`. *(Note: .cone properties are currently unavailable).* |
WARNING: The property .country_code on the AS node is often NULL. To find the registration country of an AS, you MUST traverse the relationship: (a:AS)-[:COUNTRY]-
An AS operates in multiple countries. To find its true Home/Registration Country, you MUST use the NRO relationship: (a:AS)-[:COUNTRY {reference_org: 'NRO'}]-(c:Country)(c:Country)
| `:Country` | Economy/Country. PK: `.country_code` (ISO-2). Others: `.name`, `.alpha3`, `.region_continent`, `.subregion`. |
| `:Prefix` | Generic type for IP prefixes. Properties: `.prefix`, `.af` (4 or 6). |
| `:BGPPrefix` | Subtype of Prefix announced in BGP. PK: `.prefix`. Properties: `.af` (4 or 6), `.roa_status`, `.rpki_status` (`'VALID'`, `'INVALID'`, `'NOT_FOUND'`), `.irr_status`. |
| `:GeoPrefix` | Subtype of Prefix from geolocation data. PK: `.prefix`. |
| `:RDNSPrefix` | Subtype of Prefix for reverse DNS zones. PK: `.prefix`. |
| `:RIRPrefix` / `:RPKIPrefix` / `:IANAPrefix` / `:PeeringLAN` | Subtypes of Prefix for specific allocations/registrations. PK: `.prefix`. |
| `:IP` | IPv4/IPv6 address. PK: `.ip`. Property: `.af`. Can have a `:Resolver` label. |
| `:IXP` | Internet Exchange Point. Properties: `.name`. Linked via `(:IXP)-[:COUNTRY]->(:Country)`. Size is CALCULATED via `(:AS)-[:MEMBER_OF]->(:IXP)` relationships. |
| `:URL` | A full URL string. PK: `.url` |
| `:DomainName` | DNS domain name (not FQDN). PK: `.name`. Property: `.rank` (Tranco/Umbrella global rank). |
| `:HostName` | Fully Qualified Domain Name (FQDN). PK: `.name`. |
| `:AuthoritativeNameServer` | Authoritative DNS nameserver. PK: `.name`. |
| `:Organization` | Organization loosely identified by `.name`. |
| `:Facility` | Co-location facility for IXPs/ASes. PK: `.name`. |
| `:BGPCollector` | RIPE RIS / RouteViews collector. PK: `.name`. Property: `.project`. |
| `:Tag` | Output of manual/automated classification. PK: `.label`. |
| `:Name` | A name associated to a network resource (e.g., AS name). PK: `.name`. |
| `:Ranking` | Specific ranking (e.g., Tranco, IHR). Associated via `[:RANK]` relationships. |[:RANK {rank: X}]
| `:AtlasProbe` / `:AtlasMeasurement` | RIPE Atlas entities. PK: `.id`. |
| Various IDs | `:CaidaIXID`, `:CaidaOrgID`, `:OpaqueID`, `:PeeringdbFacID`, `:PeeringdbIXID`, `:PeeringdbNetID`, `:PeeringdbOrgID`. |

---

## 3. RELATIONSHIPS & VERIFIED PROPERTIES (BY SOURCE)

### APNIC — Population & Market Share

- **Pattern:** `(:AS)-[r:POPULATION]->(:Country)`
- ✅ **KEY:** `r.percent` *(Float)*
- **Meaning:** Percentage of country population served by this AS. Used as a **proxy for Market Share**.

### Rankings (Tranco, Cisco Umbrella, CAIDA, IHR...)
- **Pattern:** `(entity)-[r:RANK]->(:Ranking)` — arrow always FROM entity TO Ranking, never reversed.
- ✅ **KEY:** `r.rank` *(Integer)*
- 🚨 **NEVER invent Ranking names.** Use only: `['Tranco top 1M', 'Cisco Umbrella Top 1 million', 'CAIDA ASRank', 'IHR country ranking: Total AS (JP)', 'IHR country ranking: Total AS (IR)']`
- For "Top N" cutoffs, filter on `r.rank`: `MATCH (a:AS)-[r:RANK]->(:Ranking {name: 'CAIDA ASRank'}) WHERE r.rank <= 50`

### IP Prefixes & Routing
- **Pattern:** `(:AS)-[:ORIGINATE]-(:Prefix)`
- **Meaning:** Connects an Autonomous System to the IP prefixes it announces. 
- 🚨 **CRITICAL RULE:** To count prefixes, ALWAYS use this undirected relationship. DO NOT use directional arrows (`->`).
- **Identifier Pattern:** `(:Prefix)-[:AVAILABLE]->(:OpaqueID)`
- **Pattern (Geographic Location of a Prefix):** `(:Prefix)-[:COUNTRY]->(:Country)`
- 🚨 **CRITICAL RULE:** To find the country of a Prefix, ALWAYS use this direct relationship. DO NOT traverse through the originating `:AS` node, as an AS can announce prefixes in multiple countries.
- 🚨 **CRITICAL RULE:** A `Prefix` is DIRECTLY connected to an `OpaqueID` via the `[:AVAILABLE]` relationship. Do NOT pass through an `:AS` node to find the OpaqueID of a prefix.
### IHR — Inter-Dependency & Resilience

- **Pattern:** `(:AS)-[d:DEPENDS_ON]->(:AS)`
- **Pattern:** `(:Prefix)-[d:DEPENDS_ON]->(:AS)`
- ✅ **KEY:** `d.hege` *(Float, 0.0–1.0)*
- **Meaning:** Hegemony score (dependency strength). High score = Risk of centralization.

- **Pattern:** `(:Prefix)-[:CATEGORIZED]->(:Tag)`
- ✅ **KEY:** `tag.label` (e.g., `'RPKI Valid'`, `'RPKI Invalid'`)

---

### OONI — Censorship, Security & Blocking

- **Pattern:** `(:AS)-[r:COUNTRY]->(:Country)`
- ✅ **KEYS:**
  - `r.percentage_tcp_blocking` *(Float, e.g., 0.15 for 15%)*
  - `r.percentage_dns_blocking`
  - `r.percentage_http_blocked`
  - `r.count_anomaly`
  > ⚠️ If 0 rows, verify keys with: `MATCH ()-[r:COUNTRY]->() RETURN keys(r)`

- **Pattern — DNSSEC Status:**
  - Check 1 *(Preferred):* `NOT (a)-[:CATEGORIZED]->(:Tag {label: 'DNSSEC_SUPPORTED'})`
  - Check 2: `(a)-[:CATEGORIZED]->(:Tag {label: 'DNSSEC_NOT_SUPPORTED'})`
  - Tag general use: `(:AS)-[:CATEGORIZED]->(t:Tag)` checking `t.label` (e.g., `'TCP_BLOCKING_HIGH'`)

---

### Cloudflare Radar — DNS & Traffic

- **Pattern:** `(:DomainName)-[q:QUERIED_FROM]->(:Country)`
- ✅ **KEY:** `q.value` *(Float)*
- **Meaning:** Share of DNS queries from this country.

---

### BGPKIT — Peering Topology

- **Pattern:** `(:AS)-[r:PEERS_WITH]->(:AS)`
- ✅ **KEY:** `r.rel` *(Integer)*
- **Values:** `0` = Peer-to-Peer, `1` = Provider-to-Customer

---

### RIPE NCC — Routing Security (RPKI)

- **Pattern:** `(:AS)-[r:ROUTE_ORIGIN_AUTHORIZATION]->(:BGPPrefix)`
- ✅ **KEY:** `r.maxLength` *(Integer)*

---

### MANRS — Routing Hygiene

- **Pattern:** `(:AS)-[:IMPLEMENT]->(:ManrsAction)`
- Properties: `.name` or `.description` on the `ManrsAction` node.

### DNS & Infrastructure Resolution
- **Full Resolution Path:** `(:DomainName)-[:PART_OF]-(:HostName)-[:RESOLVES_TO]-(:IP)-[:PART_OF]-(:Prefix)-[:ORIGINATE]-(:AS)`
- 🚨 **CRITICAL RULE:** A `DomainName` NEVER resolves directly to an `IP` or an `AS`. You MUST traverse the full path via `HostName` and `Prefix` to accurately map a domain to its hosting Autonomous System.

---

### PeeringDB — Physical Infrastructure

- **Pattern:** `(:AS)-[r:MEMBER_OF]->(:IXP)`
- ✅ **KEYS on `r`:** `r.info_ratio` (Traffic Balance), `r.info_traffic` (Volume), `r.speed`

- **Pattern:** `(:AS)-[:LOCATED_IN]->(:Facility)`

---

### Performance Metrics — RIPE Atlas / M-Lab
- Nodes: Checked directly on `:AS` or `:Country` nodes.
- ✅ **KEYS:** `.avg_rtt` (Latency), `.packet_loss` (if available)
- **Atlas Topology:** `(:AtlasMeasurement)-[:TARGET]->(n)`
- 🚨 **CRITICAL RULE:** An `AtlasMeasurement` points to its specific target (which can be an `:AS`, an `:IP`, or a `:HostName`) STRICTLY via the `[:TARGET]` relationship (singular). Do NOT invent or guess relationships like `[:TARGETS]`, `[:PROBE]`, or `[:ASSIGNED]`.
---

# 📚 Reference Query Gallery — Pattern Examples

> **Note to the Agent:** These are **structural examples only**.
> Adapt labels, relationship types, and target values based on the specific user request.
> Never reuse hardcoded values (country codes, ASNs, domain names) verbatim — always map them from the user's intent.

---

## 4.1 · Basic Lookups & Identifiers

**Find all names for a specific AS:**
```cypher
MATCH p = (:AS {asn: 99999})--(:Name)
RETURN p
```

**All nodes related to a specific Prefix:**
```cypher
MATCH p = (:Prefix {prefix: '192.0.2.0/24'})--()
RETURN p
```

**Country code of an AS via a specific reference source:**
```cypher
MATCH p = (:AS {asn: 12345})-[{reference_name: 'nro.delegated_stats'}]-(:Country)
RETURN p
```

**Number of ASes registered in a Country:**
```cypher
MATCH (a:AS)-[:COUNTRY {reference_org:'NRO'}]-(:Country {country_code:'FR'})
RETURN COUNT(DISTINCT a)
```

---

## 4.2 · Infrastructure, IXPs & Probes

**Countries of IXPs where a specific AS is present:**
```cypher
MATCH p = (:AS {asn: 64512})-[:MEMBER_OF]->(ix:IXP)--(:Country)
RETURN p
```

**IXP membership for the main ASes in a Country:**
```cypher
MATCH (a)-[:COUNTRY {reference_org:'RIPE NCC'}]-(:Country {country_code:'BR'})
MATCH (a:AS)-[ra:RANK {reference_name:"ihr.country_dependency"}]->(:Ranking)
WHERE ra.rank <= 10
OPTIONAL MATCH (a)-[m:MEMBER_OF]-(ix:IXP)-[:COUNTRY]-(:Country {country_code:'BR'})
RETURN a, m, ix
```

**Active RIPE Atlas probes for the top 5 ISPs in a Country:**
```cypher
MATCH (pb:AtlasProbe)-[:LOCATED_IN]-(a:AS)-[pop:POPULATION]-(c:Country)
WHERE c.country_code = 'CA'
  AND pb.status_name = 'Connected'
  AND pop.rank <= 5
RETURN pop.rank, a.asn, COLLECT(pb.id) AS probe_ids
ORDER BY pop.rank
```

---

## 4.3 · Topologies & Dependencies

**Main ASes in a Country (by IHR country dependency ranking):**
```cypher
MATCH (a)-[:COUNTRY {reference_org:'RIPE NCC'}]-(:Country {country_code:'DE'})
MATCH (a:AS)-[ra:RANK {reference_name:"ihr.country_dependency"}]->(r:Ranking)--(:Country {country_code:'DE'})
WHERE ra.rank < 10
OPTIONAL MATCH (a)-[:NAME {reference_org:"BGP.Tools"}]-(n:Name)
RETURN DISTINCT a.asn AS ASN,
                n.name  AS AS_Name,
                COLLECT(r.name) AS Rankings
ORDER BY a.asn
```

**Dependencies for main ASes in a Country (IHR Hegemony):**
```cypher
MATCH (a)-[:COUNTRY {reference_org:'RIPE NCC'}]-(:Country {country_code:'DE'})
MATCH (a:AS)-[ra:RANK {reference_name:"ihr.country_dependency"}]->(:Ranking)
WHERE ra.rank < 10
OPTIONAL MATCH (a)-[p:PEERS_WITH]-(b), (a)-[d:DEPENDS_ON]->(b)
WHERE p.rel = 1
  AND d.hege > 0.03
  AND a <> b
RETURN a, d, b
```

**Peer-to-peer topology for the top ASes in a Country:**
```cypher
MATCH (a:AS)-[ra:RANK]->(:Ranking {name: 'IHR country ranking: Total AS (ZA)'})<-[rb:RANK]-(b:AS)
WHERE ra.rank < 20
  AND rb.rank < 20
MATCH q = (b)-[pw:PEERS_WITH {reference_name: 'bgpkit.as2rel_v4'}]-(a)
WHERE pw.rel = 0  -- Peer-to-peer relationship only
RETURN q
```

---

## 4.4 · Domains, DNS & Traffic

**Most popular Domain Names queried from a Country:**
```cypher
MATCH (:Ranking {name: 'Tranco top 1M'})-[ra:RANK]-(dn:DomainName)-[q:QUERIED_FROM]-(c:Country)
WHERE q.value > 30
  AND c.country_code = 'IT'
RETURN dn.name    AS domain_name,
       ra.rank    AS rank,
       q.value    AS per_query_IT
ORDER BY rank
```

**IP addresses, prefixes, and ASNs related to a specific domain:**
```cypher
MATCH p = (dn:DomainName)-[:PART_OF]-(hn:HostName)
            -[:RESOLVES_TO]-(:IP)
            -[:PART_OF]-(:Prefix)
            -[:ORIGINATE {reference_org:'BGPKIT'}]-(a:AS)
WHERE dn.name = 'example.org'
  AND dn.name = hn.name
RETURN p
```

**Number of ASes hosting authoritative name servers per domain in a Country:**
```cypher
MATCH (:Ranking {name: 'Tranco top 1M'})-[ra:RANK]-(dn:DomainName)-[q:QUERIED_FROM]-(c:Country)
WHERE q.value > 30
  AND c.country_code = 'IT'
  AND ra.rank < 10000
MATCH (dn:DomainName)-[:MANAGED_BY]-(:AuthoritativeNameServer)
        -[:RESOLVES_TO]-(:IP)
        -[:PART_OF]-(:Prefix)
        -[:ORIGINATE {reference_org:'BGPKIT'}]-(a:AS)
RETURN dn.name,
       COUNT(DISTINCT a)        AS nb_asn,
       COLLECT(DISTINCT a.asn)
ORDER BY nb_asn DESC
```

---
## 5. RECOGNIZED DATA SOURCES

`APNIC` · `BGPKIT` · `BGP.Tools` · `CAIDA` · `Cisco` · `CitizenLab` · `Cloudflare` · `IHR` · `Georgia Tech` · `MANRS` · `NRO` · `OpenINTEL` · `PCH` · `PeeringDB` · `RIPE NCC` · `RouteViews` · `Stanford` · `Tranco`