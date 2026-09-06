# Content Gating

## Design profile

- **Role:** Support pattern
- **Best for:** preference control, optional-content gating, persistent content choices
- **Typical scale:** whole work
- **Can lead a phase:** No
- **Player mainly:** configure which optional content categories are enabled
- **Combines well with:** any pattern affected by the selected content preferences


This pattern handles optional-content preferences and the routing rules that respect them. Keep difficulty configuration in `settings.md` unless a project has a concrete reason to combine the two.

## Core Concepts

1. **Named Content Categories**: Define only categories that the current project actually uses. The reference should not prescribe a universal taxonomy.
2. **Safe Defaults**: Optional categories should have explicit defaults and the work should remain playable when they are disabled.
3. **Routing / Pool Gating**: Disabled content must be excluded from direct routes, wildcard pools, and random dispatchers that could otherwise reach it.
4. **Persistence**: Save preferences across sessions only when that behavior is intentional; otherwise normal Milo state is sufficient.

---

## Reusable JavaScript Engine (`milo.yaml.init`)

```yaml
modules:
  storage: {}
```

```javascript
// Project-defined content preferences
var contentPreferences = {
  categoryA: true,
  categoryB: false
};

var contentPreferencesKey = "content-preferences";

function loadContentPreferences() {
  var stored = teaseStorage.getItem(contentPreferencesKey);
  if (stored && typeof stored === "object") {
    contentPreferences.categoryA = stored.categoryA !== false;
    contentPreferences.categoryB = !!stored.categoryB;
  }
}

function saveContentPreferences() {
  teaseStorage.setItem(contentPreferencesKey, contentPreferences);
}

function contentEnabled(categoryId) {
  return contentPreferences[categoryId] === true;
}
```

---

## Milo IR Pattern: Content Preferences Menu

```yaml
pages:
  content-preferences:
    - say:
        label: "<p>Optional content preferences</p>"
    - choice:
        options:
          - label: "Toggle category A"
            commands:
              - eval:
                  script: |
                    contentPreferences.categoryA = !contentPreferences.categoryA;
                    saveContentPreferences();
              - goto:
                  target: content-preferences
          - label: "Toggle category B"
            commands:
              - eval:
                  script: |
                    contentPreferences.categoryB = !contentPreferences.categoryB;
                    saveContentPreferences();
              - goto:
                  target: content-preferences
          - label: "Continue"
            to: $opening
```

Use real project category IDs in project code. `categoryA` / `categoryB` are placeholders specifically to prevent this reference from defining one project's content taxonomy.

## Check

- Every category corresponds to content the current project actually contains.
- Disabled content has no accidental direct, wildcard, or random route.
- Defaults always lead to a playable path.
- Stored values are validated before use and can be reset.
- Difficulty, progression, and unrelated runtime systems are not bundled into content preferences without a concrete composition need.
