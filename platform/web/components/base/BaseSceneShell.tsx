"use client";

import type { CSSProperties } from "react";
import Link from "next/link";
import { useState } from "react";

import styles from "./BaseSceneShell.module.css";

export type SceneAction = {
  label: string;
  href: string;
};

type SceneMetric = {
  label: string;
  value: string;
};

type SceneRoom = {
  id: string;
  name: string;
  label: string;
  description: string;
  metrics: SceneMetric[];
  actions: SceneAction[];
  emphasis?: "hero";
};

type SceneArt = {
  imageUrl: string;
  sourceLabel: string;
  sourceHref: string;
};

export type BuildingScene = {
  id: string;
  name: string;
  district: string;
  category: string;
  verb: string;
  summary: string;
  status: string;
  accent: "copper" | "green" | "violet" | "amber" | "slate" | "blue";
  position: {
    left: string;
    top: string;
    width: string;
    height: string;
  };
  enterable: boolean;
  route: string;
  rooms: SceneRoom[];
  checklist: string[];
  silhouette: "hall" | "yard" | "academy" | "tower" | "hangar" | "dock";
  art?: SceneArt;
};

export type LandmarkScene = {
  id: string;
  name: string;
  note: string;
  accent: "stone" | "grass" | "rose";
  position: {
    left: string;
    top: string;
    width: string;
    height: string;
  };
};

type HudData = {
  operatorName: string;
  projectName: string;
  branch: string;
  tokenCost: string;
  aiCount: number;
  onlineRunners: number;
  activeTasks: number;
  blockedCount: number;
  pendingApprovals: number;
};

type SummaryItem = {
  label: string;
  value: string;
  hint: string;
};

type QueueItem = {
  title: string;
  note: string;
  href: string;
};

export function BaseSceneShell({
  hud,
  buildings,
  landmarks,
  summary,
  queue,
  projectLink,
  primaryAction,
  secondaryAction,
  quickCreate,
  initialBuildingId,
}: {
  hud: HudData;
  buildings: BuildingScene[];
  landmarks: LandmarkScene[];
  summary: SummaryItem[];
  queue: QueueItem[];
  projectLink: string;
  primaryAction: SceneAction;
  secondaryAction: SceneAction;
  quickCreate: {
    action: (payload: FormData) => void | Promise<void>;
    operator: string;
  } | null;
  initialBuildingId?: string;
}) {
  const initialId =
    buildings.find((building) => building.id === initialBuildingId)?.id ?? buildings[0]?.id ?? "";
  const [activeBuildingId, setActiveBuildingId] = useState(initialId);
  const activeBuilding = buildings.find((building) => building.id === activeBuildingId) ?? buildings[0];
  const activeTheme = getAccentTheme(activeBuilding?.accent ?? "copper");

  return (
    <main className={styles.page}>
      <div className={styles.pageGlow} />
      <div className={styles.shell}>
        <header className={styles.hero}>
          <div className={styles.heroMain}>
            <p className={styles.kicker}>OPERATIONS TOWN / BUILDING SCENES</p>
            <h1 className={styles.title}>{hud.projectName}</h1>
            <p className={styles.subtitle}>
              Separate dispatch, production, growth, approvals, hardware, and delivery into buildings that read
              clearly from the overworld, then split each building into room-scale play spaces instead of recycled
              panels.
            </p>
            <div className={styles.heroActions}>
              <Link href={primaryAction.href} className={styles.primaryButton}>
                {primaryAction.label}
              </Link>
              <Link href={secondaryAction.href} className={styles.secondaryButton}>
                {secondaryAction.label}
              </Link>
            </div>
          </div>

          <div className={styles.heroHud}>
            <div className={styles.operatorCard}>
              <span>{hud.operatorName}</span>
              <strong>Current branch: {hud.branch}</strong>
            </div>
            <div className={styles.hudGrid}>
              <div className={styles.hudCard}>
                <span>Token</span>
                <strong>{hud.tokenCost}</strong>
              </div>
              <div className={styles.hudCard}>
                <span>AI seats</span>
                <strong>{hud.aiCount}</strong>
              </div>
              <div className={styles.hudCard}>
                <span>Online devices</span>
                <strong>{hud.onlineRunners}</strong>
              </div>
              <div className={styles.hudCard}>
                <span>Production lines</span>
                <strong>{hud.activeTasks}</strong>
              </div>
              <div className={`${styles.hudCard} ${styles.hudAlert}`}>
                <span>Blocked</span>
                <strong>{hud.blockedCount}</strong>
              </div>
              <div className={`${styles.hudCard} ${styles.hudAlert}`}>
                <span>Approvals</span>
                <strong>{hud.pendingApprovals}</strong>
              </div>
            </div>
          </div>
        </header>

        <section className={styles.contentGrid}>
          <div className={styles.leftColumn}>
            <section className={styles.worldCard}>
              <div className={styles.sectionHead}>
                <div>
                  <p className={styles.kicker}>OVERWORLD</p>
                  <h2 className={styles.sectionTitle}>Town layout</h2>
                </div>
                <Link href={projectLink} className={styles.inlineLink}>
                  Project entry
                </Link>
              </div>

              <div className={styles.world}>
                <div className={styles.skyBand} />
                <div className={styles.hillBand} />
                <div className={styles.growthRidge} />
                <div className={styles.productionPlots} />
                <div className={styles.hardwareYard} />
                <div className={styles.shippingLane} />
                <div className={styles.mainRoad} />
                <div className={styles.crossRoad} />
                <div className={styles.sideRoadWest} />
                <div className={styles.sideRoadEast} />
                <div className={styles.river} />
                <div className={styles.centerPlaza} />
                <div className={styles.approvalBeacon} />

                {landmarks.map((landmark) => (
                  <div
                    key={landmark.id}
                    className={`${styles.landmark} ${styles[`landmark${capitalize(landmark.accent)}`]}`}
                    style={landmark.position}
                  >
                    <strong>{landmark.name}</strong>
                    <span>{landmark.note}</span>
                  </div>
                ))}

                {buildings.map((building) => {
                  const isActive = building.id === activeBuilding?.id;

                  return (
                    <button
                      key={building.id}
                      id={building.id}
                      type="button"
                      className={`${styles.building} ${styles[`accent${capitalize(building.accent)}`]} ${
                        styles[`silhouette${capitalize(building.silhouette)}`]
                      } ${
                        isActive ? styles.buildingActive : ""
                      }`}
                      style={building.position}
                      onClick={() => setActiveBuildingId(building.id)}
                    >
                      <span className={styles.buildingRoof} />
                      <span className={styles.buildingTag}>{building.category}</span>
                      <strong>{building.name}</strong>
                      <small>{building.verb}</small>
                      <em>{building.status}</em>
                    </button>
                  );
                })}

                <div className={styles.avatar}>
                  <span className={styles.avatarShadow} />
                  <span className={styles.avatarBody} />
                </div>

                <div className={styles.worldLegend}>
                  <strong>Read from a distance</strong>
                  <span>
                    West side is dispatch and production, the center is approvals, the east side is delivery and
                    hardware, and the northeast corner is growth.
                  </span>
                </div>

                {activeBuilding ? (
                  <aside className={styles.mapFocus}>
                    <span className={styles.mapFocusLabel}>Map focus</span>
                    <strong>{activeBuilding.name}</strong>
                    <p>{activeBuilding.verb}</p>
                    <em>{activeBuilding.status}</em>
                  </aside>
                ) : null}
              </div>

              <div className={styles.districtGrid}>
                {buildings.map((building) => {
                  const isActive = building.id === activeBuilding?.id;

                  return (
                    <button
                      key={`${building.id}-rail`}
                      type="button"
                      className={`${styles.districtCard} ${
                        isActive ? styles.districtCardActive : ""
                      } ${styles[`district${capitalize(building.accent)}`]}`}
                      onClick={() => setActiveBuildingId(building.id)}
                    >
                      <span>{building.category}</span>
                      <strong>{building.name}</strong>
                      <p>{building.summary}</p>
                    </button>
                  );
                })}
              </div>
            </section>

            {activeBuilding ? (
              <section className={styles.interiorCard} style={activeTheme}>
                <div className={styles.sectionHead}>
                  <div>
                    <p className={styles.kicker}>INTERIOR</p>
                    <h2 className={styles.sectionTitle}>{activeBuilding.name}</h2>
                  </div>
                  <Link href={activeBuilding.route} className={styles.inlineLink}>
                    Open live page
                  </Link>
                </div>

                <div className={styles.interiorHero}>
                  <div>
                    <div className={styles.pillRow}>
                      <span className={styles.categoryPill}>{activeBuilding.category}</span>
                      <span className={styles.categoryPill}>{activeBuilding.district}</span>
                    </div>
                    <p className={styles.interiorSummary}>{activeBuilding.summary}</p>
                    <div className={styles.flowRail}>
                      {activeBuilding.rooms.map((room, index) => (
                        <div key={`${room.id}-flow`} className={styles.flowStop}>
                          <span>{String(index + 1).padStart(2, "0")}</span>
                          <strong>{room.name}</strong>
                        </div>
                      ))}
                    </div>
                  </div>
                  {activeBuilding.art ? (
                    <div className={styles.interiorArtCard}>
                      <div
                        className={styles.interiorArtImage}
                        style={{ backgroundImage: `url(${activeBuilding.art.imageUrl})` }}
                      />
                      <div className={styles.interiorArtMeta}>
                        <span>Reference asset</span>
                        <strong>{activeBuilding.art.sourceLabel}</strong>
                        <Link href={activeBuilding.art.sourceHref} className={styles.inlineLink}>
                          Open source
                        </Link>
                      </div>
                    </div>
                  ) : null}
                  <div className={styles.interiorStatus}>
                    <span>Status</span>
                    <strong>{activeBuilding.status}</strong>
                    <small>{activeBuilding.verb}</small>
                  </div>
                </div>

                <div className={styles.roomGrid}>
                  {activeBuilding.rooms.map((room) => (
                    <article
                      key={room.id}
                      className={`${styles.roomCard} ${room.emphasis === "hero" ? styles.roomHero : ""}`}
                    >
                      <div className={styles.roomHead}>
                        <span className={styles.roomLabel}>{room.label}</span>
                        <h3>{room.name}</h3>
                      </div>
                      <p className={styles.roomDescription}>{room.description}</p>
                      <div className={styles.metricGrid}>
                        {room.metrics.map((metric) => (
                          <div key={`${room.id}-${metric.label}`} className={styles.metricCard}>
                            <span>{metric.label}</span>
                            <strong>{metric.value}</strong>
                          </div>
                        ))}
                      </div>
                      <div className={styles.roomActions}>
                        {room.actions.map((action) => (
                          <Link key={`${room.id}-${action.href}`} href={action.href} className={styles.roomLink}>
                            {action.label}
                          </Link>
                        ))}
                      </div>
                    </article>
                  ))}
                </div>

                <div className={styles.checklistCard}>
                  <h3>Scene checks</h3>
                  <div className={styles.checklist}>
                    {activeBuilding.checklist.map((item) => (
                      <div key={item} className={styles.checkItem}>
                        {item}
                      </div>
                    ))}
                  </div>
                </div>
              </section>
            ) : null}
          </div>

          <div className={styles.rightColumn}>
            {activeBuilding ? (
              <section className={styles.sideCard} style={activeTheme}>
                <div className={styles.sectionHead}>
                  <div>
                    <p className={styles.kicker}>ACTIVE DISTRICT</p>
                    <h2 className={styles.sectionTitle}>{activeBuilding.name}</h2>
                  </div>
                  <Link href={activeBuilding.route} className={styles.inlineLink}>
                    Open route
                  </Link>
                </div>
                <div className={styles.activeDistrictCard}>
                  <span className={styles.activeDistrictTag}>{activeBuilding.category}</span>
                  <strong>{activeBuilding.verb}</strong>
                  <p>{activeBuilding.summary}</p>
                  <div className={styles.activeDistrictMeta}>
                    <div>
                      <span>District</span>
                      <strong>{activeBuilding.district}</strong>
                    </div>
                    <div>
                      <span>Status</span>
                      <strong>{activeBuilding.status}</strong>
                    </div>
                  </div>
                  {activeBuilding.art ? (
                    <div className={styles.activeDistrictArt}>
                      <div
                        className={styles.activeDistrictArtImage}
                        style={{ backgroundImage: `url(${activeBuilding.art.imageUrl})` }}
                      />
                      <div className={styles.activeDistrictArtMeta}>
                        <span>Adapted from</span>
                        <Link href={activeBuilding.art.sourceHref} className={styles.inlineLink}>
                          {activeBuilding.art.sourceLabel}
                        </Link>
                      </div>
                    </div>
                  ) : null}
                  <div className={styles.activeDistrictChecks}>
                    {activeBuilding.checklist.map((item) => (
                      <div key={`${activeBuilding.id}-${item}`} className={styles.activeDistrictCheck}>
                        {item}
                      </div>
                    ))}
                  </div>
                </div>
              </section>
            ) : null}

            <section className={styles.sideCard}>
              <div className={styles.sectionHead}>
                <div>
                  <p className={styles.kicker}>DISTRICTS</p>
                  <h2 className={styles.sectionTitle}>Quick read</h2>
                </div>
              </div>
              <div className={styles.summaryList}>
                {summary.map((item) => (
                  <article key={item.label} className={styles.summaryItem}>
                    <div>
                      <strong>{item.label}</strong>
                      <p>{item.hint}</p>
                    </div>
                    <span>{item.value}</span>
                  </article>
                ))}
              </div>
            </section>

            <section className={styles.sideCard}>
              <div className={styles.sectionHead}>
                <div>
                  <p className={styles.kicker}>NEXT STOPS</p>
                  <h2 className={styles.sectionTitle}>Where to go</h2>
                </div>
              </div>
              <div className={styles.queueList}>
                {queue.map((item) => (
                  <Link key={item.title} href={item.href} className={styles.queueItem}>
                    <strong>{item.title}</strong>
                    <span>{item.note}</span>
                  </Link>
                ))}
              </div>
            </section>

            {quickCreate ? (
              <section className={styles.sideCard}>
                <div className={styles.sectionHead}>
                  <div>
                    <p className={styles.kicker}>QUICK REGISTER</p>
                    <h2 className={styles.sectionTitle}>Start a new base</h2>
                  </div>
                </div>
                <form action={quickCreate.action} className={styles.quickForm}>
                  <input type="hidden" name="project_type" value="software" />
                  <input type="hidden" name="default_branch" value="main" />
                  <input type="hidden" name="develop_branch" value="develop" />
                  <input className={styles.textField} name="name" placeholder="Project name" required />
                  <textarea
                    className={styles.textArea}
                    name="description"
                    rows={4}
                    placeholder={`Write the scope for a new base opened by ${quickCreate.operator}.`}
                  />
                  <button type="submit" className={styles.primaryButton}>
                    Create and enter
                  </button>
                </form>
              </section>
            ) : null}
          </div>
        </section>
      </div>
    </main>
  );
}

function capitalize(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function getAccentTheme(accent: BuildingScene["accent"]): CSSProperties {
  const themes: Record<BuildingScene["accent"], CSSProperties> = {
    copper: {
      "--scene-accent": "#b75f35",
      "--scene-soft": "rgba(242, 202, 174, 0.48)",
      "--scene-deep": "#6c3921",
    } as CSSProperties,
    green: {
      "--scene-accent": "#4d8e37",
      "--scene-soft": "rgba(194, 235, 169, 0.52)",
      "--scene-deep": "#245124",
    } as CSSProperties,
    violet: {
      "--scene-accent": "#6e58bf",
      "--scene-soft": "rgba(210, 200, 255, 0.52)",
      "--scene-deep": "#413288",
    } as CSSProperties,
    amber: {
      "--scene-accent": "#b7831f",
      "--scene-soft": "rgba(255, 225, 158, 0.52)",
      "--scene-deep": "#6b4d0d",
    } as CSSProperties,
    slate: {
      "--scene-accent": "#4a6776",
      "--scene-soft": "rgba(192, 216, 228, 0.52)",
      "--scene-deep": "#243846",
    } as CSSProperties,
    blue: {
      "--scene-accent": "#336ea9",
      "--scene-soft": "rgba(181, 214, 247, 0.52)",
      "--scene-deep": "#1f4772",
    } as CSSProperties,
  };

  return themes[accent];
}
