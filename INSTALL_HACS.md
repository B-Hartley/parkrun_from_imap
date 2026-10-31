# Installing through HACS (older Home Assistant installations)

Use these instructions when your Home Assistant installation has **HACS**, rather than the newer **Marketplace** interface.

1. Ensure [HACS](https://www.hacs.xyz/docs/use/download/download/) is installed and configured.
2. Open [Parkrun from IMAP in HACS](https://my.home-assistant.io/redirect/hacs_repository/?owner=B-Hartley&repository=parkrun_from_imap&category=integration).
3. If the link does not add it, open **HACS → ⋮ → Custom repositories**, enter `https://github.com/B-Hartley/parkrun_from_imap`, and choose **Integration**.
4. Download **Parkrun from IMAP**.
5. Restart Home Assistant.
6. Go to **Settings → Devices & services → Add integration**, find **Parkrun from IMAP**, and add a runner using their athlete barcode and name.

Afterwards, return to the [main setup guide](README.md#2-import-your-complete-running-history) to import your results and configure email processing.

Do not install the separate older `parkrun5k` repository. This one is `parkrun_from_imap`.
