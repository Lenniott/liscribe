```
Footer;
            with Horizontal(classes="footer-container"):
                yield Button("^c Back to preferences", id="btn-back", classes="btn secondary inline hug-row")
                yield Static("", classes="spacer-row")
                yield Button("Save", id="btn-save", classes="btn primary inline hug-row")

Must change any buttons that are basically back a page to now be btn-back
and any save sumbit etc as btn-save
```

```
headers:
Large:

Small: