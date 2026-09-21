# Prospective Windows Time polling correction

Evidence: first D5.1 smoke has recorded W32TIME_SYNC_ERROR after ~15 min, although independent NTP offsets stayed <24 ms. Registry: NtpServer=time.windows.com,0x9, SpecialPollInterval=32768 s, MinPollInterval=10, MaxPollInterval=15. Peers query: next request >31000 s; peer last-sync error0 differs from status stale-sample error2. No SPIKE state or packet loss is proven. The long refresh schedule is a concrete environment mismatch with the predeclared recent-sync requirement.

Proposed reversible repair for FUTURE measurements only: retain time.windows.com, choose standard client flag0x8, and MinPollInterval6 / MaxPollInterval9 (64..512 s). Use documented w32tm /config /update, then normal /resync. Keep all acceptance criteria, raw samples and first-smoke FAIL unchanged. Never set the wall clock manually. Save original parameters and rollback on configuration failure; preserve SpecialPollInterval itself. No service/process restart or historical DB access required.

The repair is not considered successful until independent probes and W32Time show regular fresh successful synchronizations over time. No new smoke until full current review ends and code/test provenance has been checked.

Sources: https://learn.microsoft.com/en-us/windows-server/networking/windows-time-service/windows-time-service-tools-and-settings ; https://learn.microsoft.com/en-us/windows-server/networking/windows-time-service/configuring-systems-for-high-accuracy ; https://learn.microsoft.com/en-us/troubleshoot/windows-server/active-directory/specialpollinterval-polling-interval-time-service-not-correct . The SPIKE article documents the flag semantics, not proof that this host experienced SPIKE.
