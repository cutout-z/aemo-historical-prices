# VPS Monthly Updates

Production model:

- Hetzner VPS runs the monthly data refresh and keeps only a bounded recent raw cache.
- GitHub stores code and publishable `outputs/`.
- GitHub Pages deploys after the VPS pushes updated outputs.
- GitHub Actions remains available for manual verification, but should not be the primary scheduled data runner.

## Lane

| Lane | Timer | Pipeline args | Purpose |
| --- | --- | --- | --- |
| Monthly historical prices | `aemo-historical-prices.timer` | `--months-back 2` | Reprocess the recent complete-month overlap window, preserve settled nominal history, regenerate CPI-adjusted outputs and workbooks. |

Recommended layout:

```text
/opt/aemo-historical-prices      git checkout + virtualenv
/etc/aemo-historical-prices/env  service settings
```

Create `/etc/aemo-historical-prices/env` from `env.example`. The service user needs a repo-scoped deploy key that can push to `cutout-z/aemo-historical-prices`.

## Install Timer

```bash
sudo cp deploy/aemo-historical-prices.service /etc/systemd/system/
sudo cp deploy/aemo-historical-prices.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now aemo-historical-prices.timer
```

Run once manually:

```bash
sudo systemctl start aemo-historical-prices.service
journalctl -u aemo-historical-prices.service -f
```
