# Monorepo source provenance

`source-map.json` is the machine-readable record of the histories imported into
`https://github.com/HalloYang06/PSOC_E84_robot` on `main`. The original source SHA for each import is
preserved unchanged as the second parent of its integration merge. This makes the
original object identity auditable without depending on a live source branch.

| Component | Source repository | Source ref | Original source SHA | Integration merge | Monorepo target |
| --- | --- | --- | --- | --- | --- |
| m33 | `https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator` | `M33` | `24bae363c50a221dbbaf61c041dfa501a9e539b4` | `dc68d812d07eaafcd73f51e5253c688e3914825c` | `firmware/m33` |
| m55 | `https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator` | `M55` | `7298c28e81b43fdb5b37e84408cfc62895eaea85` | `85ea91c72e2e058ea9f53e149bfc91cb21d49799` | `firmware/m55` |
| c8t6 | `https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator` | `C8T6` | `28b79a09dd4813fb31cc776f402183a75ed0e153` | `14b4ee0c4edaaf13edb00c23de4f5410d3c9e384` | `firmware/c8t6` |
| ros | `https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator` | `feature/rehab-arm-ros2-architecture` | `69450f7165e608f99fc4b574beffa5ac50d2331f` | `440efc9c87577d662f4ae6abe3413a50e8f1692f` | `ros/rehab_arm_ws` |
| rehab-platform | `https://github.com/wenjunyong666/ai-` | `app/rehab-arm-mobile-stitch` | `f6c2c026ce6acda074608aa3e3ada880d62c62d3` | `48c5dbd5b47e4c37206980906000a79a1fe9b890` | `apps/mobile`, `platform` |
| vla | `https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator` | `ai` | `517df8f37105f659f2fe3561b46540ced830c731` | `c5d41d5ea4d7d194615fbc49e21edc840710c6cc` | `ai/vla` |

## Source path mappings

| Component | Source path | Target path |
| --- | --- | --- |
| m33 | `.` | `firmware/m33` |
| m55 | `.` | `firmware/m55` |
| c8t6 | `.` | `firmware/c8t6` |
| ros | `rehab_arm_ros2_ws` | `ros/rehab_arm_ws` |
| rehab-platform | `apps/mobile/rehab-arm-android` | `apps/mobile` |
| rehab-platform | `apps/web` | `platform/web` |
| rehab-platform | `apps/api` | `platform/api` |
| rehab-platform | `apps/runner` | `platform/runner` |
| rehab-platform | `packages/shared` | `platform/shared` |
| rehab-platform | `infra` | `platform/deploy` |
| rehab-platform | `package.json` | `platform/package.json` |
| rehab-platform | `package-lock.json` | `platform/package-lock.json` |
| vla | `vla_system` | `ai/vla` |

## Reading imported history

An ordinary path-limited log under a new monorepo prefix starts at the integration
merge. Earlier commits used their original, unprefixed paths, so Git cannot infer
the prefix change by walking `git log --follow` across the merge. Inspect the
integration merge and then query its second parent with the original source path.
The recorded SHA and second-parent relationship are the stable provenance links.

## Deliberate exclusions

- Temporary M33 and M55 recovery branches are not canonical imports. Their work
  must be reviewed and promoted to the corresponding source branch before a later
  monorepo import.
- `NanoPi_ROSNode`, a direct CAN master, remains bench-only and is not part of the
  formal ROS 2 workspace.
- Old APP copies and generated build output were superseded by `apps/mobile`.
- `ROS_VLA_WebSocket` is historical rather than part of the formal ROS import.
- Harvest Moon/farm game static assets under `2d-upgrade` and `lib/game` were
  excluded, as were generated APK files.
- Historical web copies were excluded; `platform/web` is the canonical imported
  web application.
- The old repository's live `ai` ref may now be absent. Its exact source commit,
  `517df8f37105f659f2fe3561b46540ced830c731`, is preserved locally as the second
  parent of the VLA integration merge.

## Verification

Run from the repository root:

```sh
python -m json.tool docs/migration/source-map.json
pytest -q tools/test/test_history_provenance.py
pytest -q tools/test
git cat-file -t 24bae363c50a221dbbaf61c041dfa501a9e539b4
git rev-parse dc68d812d07eaafcd73f51e5253c688e3914825c^2
git merge-base --is-ancestor dc68d812d07eaafcd73f51e5253c688e3914825c HEAD
```
