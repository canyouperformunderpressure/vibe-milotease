# Map Exploration & Free-Roaming Navigation

## Design profile

- **Role:** Anchor pattern
- **Best for:** agency, exploration, discovery, route planning
- **Typical scale:** phase / whole work
- **Can lead a phase:** Yes
- **Player mainly:** choose destinations, search locations, unlock routes and revisit places
- **Combines well with:** `random-encounters.md`, `progression.md`, `save-resume.md`


This mechanic provides structured spatial exploration across interconnected locations while tracking visits, route access, discoveries, and optional encounter opportunities.

## Core Concepts

1. **Map Topology**: A directed or bidirectional graph of Pages/Outline nodes representing locations.
2. **Route Metadata**: Optional route labels such as `main-route`, `side-route`, `locked-route`, or project-defined terrain tags can affect presentation or rules without changing the graph model.
3. **Discovery / Objective Progress**: Track only discoveries that change later navigation, available actions, or completion conditions.
4. **Location State**: Track visits, one-time discoveries, local state, or cleared events only when revisiting a location needs to behave differently.
5. **Encounter Hooks**: Entry, search, rest, or travel actions may dispatch another pattern such as `random-encounters.md`; exploration itself should not assume a particular encounter theme.

---

## Reusable JavaScript Engine (`milo.yaml.init`)

```javascript
// Map Exploration State
var currentLocation = "entry-area";
var visitedLocations = {};
var objectiveProgress = 0; // Optional normalized progress: 0 to 100
var discoveries = {};
var routeAccess = {};

function visitLocation(nodeId) {
  currentLocation = nodeId;
  if (!visitedLocations[nodeId]) {
    visitedLocations[nodeId] = 1;
  } else {
    visitedLocations[nodeId]++;
  }
}

function recordDiscovery(discoveryId, amount) {
  if (!discoveries[discoveryId]) {
    discoveries[discoveryId] = true;
    objectiveProgress = Math.min(100, objectiveProgress + (amount || 0));
  }
}

function setRouteAccess(routeId, enabled) {
  routeAccess[routeId] = !!enabled;
}

function canUseRoute(routeId) {
  return routeAccess[routeId] !== false;
}
```

---

## Milo IR Patterns: Map Navigation Node

```yaml
pages:
  node-entry:
    - eval:
        script: visitLocation("entry-area");
    - say:
        label: |
          <p><strong>Entry Area</strong></p>
          <p>This location connects the main route, a side route, and one searchable point of interest.</p>
    - choice:
        options:
          - label: "Take the main route"
            to: $main-route
          - label: "Take the side route"
            to: $side-route
          - label: "Search the area"
            to: search-area
```

The example intentionally uses neutral location and objective names. Put setting-specific geography, collectibles, factions, and completion conditions in the project Outline/content rather than in this pattern.

## Check

- Every visible route points to a reachable Page or allowed Outline exit.
- Revisit behavior is explicit when a location can be entered more than once.
- Discovery state exists only when it changes later behavior.
- Completion is based on project-defined conditions, not assumptions built into the exploration engine.
- Encounter themes remain outside this pattern unless the project explicitly composes them in.
