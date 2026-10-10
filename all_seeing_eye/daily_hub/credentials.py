"""Use the environment or macOS Keychain; never store API keys in run files."""
import os
import subprocess

SERVICES = {
    "the_odds_api": ("Model4 Daily Baseball Odds API", ("ODDS_API_KEY", "THE_ODDS_API_KEY")),
    "oddsblaze": ("Model4 Daily Baseball OddsBlaze", ("ODDSBLAZE_API_KEY",)),
    "odds_papi": ("Model4 Daily Baseball OddsPapi", ("ODDSPAPI_API_KEY", "ODDS_PAPI_API_KEY")),
}
ACCOUNT = "daily-baseball"


def read_key(provider: str = "the_odds_api") -> str:
    service, names = SERVICES[provider]
    configured = next((os.environ[name] for name in names if os.environ.get(name)), "")
    if configured:
        return configured
    try:
        result = subprocess.run(["/usr/bin/security", "find-generic-password", "-s", service, "-a", ACCOUNT, "-w"],
                                capture_output=True, text=True, timeout=5)
        return result.stdout.strip() if result.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def save_key(value: str, provider: str = "the_odds_api") -> None:
    if not value.strip():
        raise ValueError("Enter this provider's API key first.")
    service, _ = SERVICES[provider]
    result = subprocess.run(["/usr/bin/security", "add-generic-password", "-U", "-s", service,
                             "-a", ACCOUNT, "-w", value.strip()], capture_output=True, timeout=15)
    if result.returncode:
        raise RuntimeError("macOS Keychain did not save the key. The entered key can still be used for this session.")
