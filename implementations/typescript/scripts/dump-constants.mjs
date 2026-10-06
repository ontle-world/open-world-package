// Print the closed lists and tables the TypeScript implementation keeps, as JSON, for
// tests/test_implementation_constants.py to compare with the Python reference's. Run after `npm run build`.
import { PROFILES } from "../dist/context.js";
import { DOCUMENT_KINDS, IGNORED } from "../dist/discovery.js";
import { IGNORE_FILE } from "../dist/ignore.js";
import { CARD_SECTIONS, CARD_SPEC_KEY, DEFAULT_CARDS, DESCRIPTION_LIMIT, TEMPLATE_CARD_TEXT } from "../dist/report.js";
import { DEPENDENCY_DIRECTIONS, LOCK_FORMAT } from "../dist/resolve.js";
import { RESERVED_EXTENSION_NAMES } from "../dist/structure.js";
import { API_VERSION, LEGACY_MANIFEST_NAMES, PACKAGE_KINDS } from "../dist/vocab.js";
import { ACTOR_BLOCKS, FAMILIES, OPEN_VALUE_SETS } from "../dist/rules/experimental.js";
import { PROVIDERS } from "../dist/rules/externalref.js";
import { FORMATS, ONTOLOGY_PROFILES, ROLES, TERM_TYPES } from "../dist/rules/ontology.js";
import { AGGREGATE_FUNCTIONS, CONDITIONS, SELECTORS } from "../dist/rules/world.js";

const sorted = (xs) => [...xs].sort();
console.log(JSON.stringify({
  apiVersion: API_VERSION,
  packageKinds: sorted(PACKAGE_KINDS),
  legacyManifests: sorted(LEGACY_MANIFEST_NAMES),
  documentKinds: sorted(DOCUMENT_KINDS),
  ignoredPathParts: sorted(IGNORED),
  ignoreFile: IGNORE_FILE,
  lockFormat: LOCK_FORMAT,
  worldProfiles: [...PROFILES],
  ontologyProfiles: [...ONTOLOGY_PROFILES],
  ontologyFormats: sorted(FORMATS),
  ontologyRoles: sorted(ROLES),
  termTypes: sorted(TERM_TYPES),
  providers: sorted(PROVIDERS),
  reservedExtensionNames: sorted(RESERVED_EXTENSION_NAMES),
  selectors: sorted(SELECTORS),
  aggregateFunctions: sorted(AGGREGATE_FUNCTIONS),
  conditions: sorted(CONDITIONS),
  actorBlocks: [...ACTOR_BLOCKS],
  families: FAMILIES,
  openValueSets: sorted(OPEN_VALUE_SETS),
  dependencyDirections: Object.fromEntries(Object.entries(DEPENDENCY_DIRECTIONS).map(([k, v]) => [k, sorted(v)])),
  cardSections: CARD_SECTIONS,
  defaultCards: DEFAULT_CARDS,
  cardSpecKey: CARD_SPEC_KEY,
  descriptionLimit: DESCRIPTION_LIMIT,
  templateCardText: TEMPLATE_CARD_TEXT,
}, null, 2));
