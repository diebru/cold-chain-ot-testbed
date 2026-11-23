# Cold Chain OT Testbed

[Versione italiana](README.md) · English

A testbed for the security of connected commercial refrigeration. It starts from a real case, the sabotage campaigns against the refrigeration systems of European retail chains in October and November 2026, and reproduces its **class of weakness** on devices I own: management functions reachable from the network and poorly protected. The testbed comes in two versions, **vulnerable** and **hardened**, and measures the effect of each defense against the same attacks.

3-credit project work for the Cybersecurity course, Master's Degree in Computer Engineering, University of Bologna.

> **Status:** in progress. The case study is complete, the testbed is under development.

## Contents

| Part | Status |
|---|---|
| [Case study](case-study/case_study.pdf) (PDF, 13 pages, in Italian) | Complete |
| Threat model with MITRE ATT&CK for ICS | In progress |
| Vulnerable testbed in Docker: simulated controller (web and Modbus/TCP), MQTT broker, alarm server | To do |
| Three attack scenarios: setpoint and defrost tampering, spoofed or replayed readings, sensor silencing | To do |
| Hardened testbed: segmentation, firewall, WireGuard VPN, authentication, TLS, signed readings, heartbeat, independent sensor | To do |
| Port to Raspberry Pi with a real temperature sensor (DS18B20) | To do |
| Physical anomaly detection and before/after results table | To do |

---

## Case study: the attack on the refrigeration systems of European retail chains

**Full document (Italian):** [case-study/case_study.pdf](case-study/case_study.pdf). A threat-intelligence-style report (TLP:CLEAR) with confidence levels, timeline, technical analysis, attribution, impacts, MITRE ATT&CK for ICS mapping and source references. Public sources consulted on 23 November 2026.

### Executive summary

During the night of 11 to 12 October 2026, an attacker remotely changed the defrost parameters of the refrigeration supervisors in about **700 stores** of French retail chains, driving display cases and cold rooms to high temperatures. The result was tens of millions of euros of spoiled goods and at least **15 fire outbreaks**. A second wave, during the night of 1 to 2 November, hit about ten European countries, **including Italy**, and three sites of the Établissement français du sang (EFS), the French blood service.

The attack required no malware. It was enough to find the management interfaces exposed on the Internet, often on end-of-life models, and use their built-in functions. It is a textbook OT case: no data was stolen, yet changing one parameter caused physical damage. The order of priorities is therefore safety, availability, integrity and only last confidentiality.

### Key findings

| # | Confidence | Finding |
|---|---|---|
| 1 | High | The first wave hit about 700 sites in France, with forced defrost cycles up to about 50 °C and at least 15 fire outbreaks. |
| 2 | High | The second wave hit about ten European countries, including Italy, and three EFS sites. |
| 3 | Moderate | The French government attributes the first wave to the Shahid Kaveh unit of Iran's IRGC. The forensic evidence has not been published. |
| 4 | High | The targets were found with the FOFA device search engine. |
| 5 | Low | The access vector is unclear: factory default credentials or the CVE-2025-41450 authentication bypass. |
| 6 | High | No malware: only legitimate interface functions were used. |
| 7 | High | At the EFS, a monitoring system independent from the compromised vendor prevented the loss of the products. |

### The attack chain and the defenses that would have stopped it

| Step | What happened | Measure that would have stopped it |
|---|---|---|
| 1. Discovery | FOFA, Shodan and Censys find thousands of exposed supervisors | No public IP: segmentation, access only through a VPN |
| 2. Access | Web interface: factory default credentials or CVE-2025-41450 | Strong and unique credentials, MFA, updated firmware |
| 3. Action | Setpoints, defrost and alarm thresholds changed with legitimate commands | Least privilege: maintainers change only what they need |
| 4. Damage | Spoiled goods, at least 15 fire outbreaks | Independent alarm, as at the EFS: damage avoided |

All these measures were known and recommended before the attack.

### Recommendations

1. Take the supervisors off the Internet: no management interface on a public IP.
2. Maintainer access only through a VPN with multi-factor authentication.
3. Change factory default credentials, update firmware, enable restrictive security modes.
4. Replace end-of-life devices and keep an inventory of exposed assets.
5. Add an independent temperature alarm alongside the vendor's supervision.

### From the case to the testbed

| Lesson from the case | In the testbed |
|---|---|
| Reaching the interface and using its built-in functions was enough | **Scenario 1:** setpoint change and forced defrost on a web and Modbus/TCP interface with no authentication |
| Whoever controls the measurement channel can hide the attack | **Scenario 2:** spoofed or replayed MQTT readings |
| The attackers also changed the alarm thresholds | **Scenario 3:** sensor silencing so that the alarm does not fire |
| Exposure on a public IP and remote maintenance | Segmentation, firewall, maintainer access only through a WireGuard VPN |
| Factory default credentials and weak authentication | Authentication on the web interface and MQTT, TLS on the channel |
| Unverifiable measurements | Signed and timestamped readings: a replayed message is discarded |
| Independent monitoring worked at the EFS | Heartbeat (missing data is an alarm too) and a second sensor on an Arduino, connected over USB and off the network |
| The damage was discovered in the morning | Physical anomaly detection: setpoints changed outside working hours, unscheduled defrost cycles, impossible temperature curves |

---

## Scope and responsible use

- The testbed runs only on **devices I own**, on an **isolated network**, with no contact with real supervisors.
- It does not exploit vulnerabilities in commercial products. It reproduces the observed class of weakness, that is built-in functions left unprotected, **not** any specific vendor's product.
- The case study contains no attack code, algorithms, credentials, device search queries or technical indicators of compromise.
- The goal of the work is **defensive**: showing which measures stop the attack and what they cost.

## Repository structure

```
case-study/    the case study as a PDF (Italian)
vulnerable/    the vulnerable testbed (coming soon)
hardened/      the hardened testbed (coming soon)
docs/          threat model and final report (coming soon)
```

## Author

Diego Bruno, Master's Degree in Computer Engineering, University of Bologna.
