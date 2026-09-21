# Prospective fixed 64-second polling trial

The adaptive 64..512 s trial is NOT validated: all 11 observations remain in clock_polling_fix; the last reports W32Time error2 with last-good age213.219 s. A subsequent peer query shows reachability255, peer error0, interval256s and a new successful sync exactly256s after the prior one. This supports a stale discipline sample between scheduled polls, not proof of unreachable NTP or excessive independent offsets.

Next reversible technical trial: MinPollInterval=MaxPollInterval=6 (64s), the polling values documented by Microsoft for high accuracy configurations. Keep the same server and flag0x8, all other settings and ALL D5.1 acceptance thresholds. No manual time setting, no registry execution-policy change, no service restart. Save before/after and normal resync result. This is not a claim of 1ms Internet accuracy. Observe twenty minutes before considering the trial validated; any failed probe is retained and blocks launch under unchanged criteria.

Reference: https://learn.microsoft.com/en-us/windows-server/networking/windows-time-service/configuring-systems-for-high-accuracy#registry-settings . No historical DB, timestamp or prior verdict is changed. No new market collection while clock validation is pending.
