# Notes

Notes are where you write things down: how a system is set up, runbooks, checklists, decisions.

## Write a note

1. Open **Notes** and click **New note**.
2. Give it a name and write in Markdown. The **Preview** tab shows the result.
3. Optionally add tags and link the note to devices.

Markdown basics:

```markdown
# Heading
## Smaller heading

Normal text with **bold** and *italic*.

- a list item
- another one

1. a numbered step
2. the next step

`inline code` and a code block:

    ```bash
    ping 10.0.0.1
    ```

[A link](https://example.com)

| Column | Column |
|---|---|
| value | value |
```

Code blocks get syntax colouring and a copy button.

## Names

A note's name is also its file name, so spaces become underscores: "Backup runbook" is stored and shown as `Backup_runbook`. Pick names that read well that way.

## Tags and devices

- **Tags** group notes. On the notes page, click a tag to see only those notes.
- **Linked devices** make a note appear on the device's page, and the other way round.

## Search

The search box at the top searches note names, tags and the text inside notes, together with devices and credentials. Press `/` to jump to it.

## Notes are files

Each note is a Markdown file in the `./notes` folder of your install, with its tags and device links in a small `.meta.json` file next to it. That makes notes easy to back up and read outside PrivateGlue. If you edit the files directly, set `PUID` and `PGID` to your own user id (see [Configuration](Configuration)) so the app and you can both write them.

To keep notes in a Git repository with history, see the GitHub notes sync under [Integrations](Integrations).

## Images

A note can show an image that is hosted elsewhere, as long as its address starts with `https://`. Images cannot be uploaded into PrivateGlue.
