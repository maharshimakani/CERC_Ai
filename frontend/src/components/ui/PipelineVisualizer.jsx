/**
 * PipelineVisualizer.jsx — Upgraded with agent-plan.tsx animation patterns
 * ─────────────────────────────────────────────────────────────────────────
 * Effects integrated from agent-plan.tsx:
 *   ✔ Spring-physics accordion expand/collapse (LayoutGroup + layout prop)
 *   ✔ Staggered child step reveals (staggerChildren + custom Apple easing)
 *   ✔ Status icon AnimatePresence transitions (rotate + scale on change)
 *   ✔ Status badge bounce animation on status change (key-based re-mount)
 *   ✔ Vertical dashed connecting line between section header and steps
 *   ✔ Row hover micro-animation (subtle bg shift)
 *   ✔ prefers-reduced-motion respected throughout
 *
 * Design principles (unchanged):
 *   ✔ Zero random/playful behavior — all data-driven
 *   ✔ Matches existing CSS design tokens
 *   ✔ Section isolation — each section independently traceable
 */

import { useState } from 'react'
import { motion, AnimatePresence, LayoutGroup } from 'framer-motion'

// ── prefers-reduced-motion ───────────────────────────────────────────────────
const prefersReducedMotion =
  typeof window !== 'undefined' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches

// ── Apple-like easing curve (from agent-plan.tsx) ────────────────────────────
const APPLE_EASE = [0.2, 0.65, 0.3, 0.9]
const SPRING_OPTS = prefersReducedMotion
  ? { type: 'tween', duration: 0.15 }
  : { type: 'spring', stiffness: 500, damping: 30 }

// ── Static pipeline step definitions ─────────────────────────────────────────
const PIPELINE_STEPS = ['Load', 'Extract', 'Map', 'Generate', 'Validate']

// ── Status config ─────────────────────────────────────────────────────────────
const STATUS_CONFIG = {
  complete: {
    color: 'var(--success, #10b981)',
    bg: 'rgba(16,185,129,0.12)',
    label: 'COMPLETE',
    dot: '#10b981',
  },
  partial: {
    color: 'var(--warning, #f59e0b)',
    bg: 'rgba(245,158,11,0.12)',
    label: 'PARTIAL',
    dot: '#f59e0b',
  },
  missing: {
    color: 'var(--danger, #ef4444)',
    bg: 'rgba(239,68,68,0.12)',
    label: 'MISSING',
    dot: '#ef4444',
  },
}

// ── Animation variants (adapted from agent-plan.tsx) ──────────────────────────

/** Outer section row: fade + subtle slide in */
const sectionVariants = {
  hidden: { opacity: 0, y: prefersReducedMotion ? 0 : -6 },
  visible: {
    opacity: 1, y: 0,
    transition: { ...SPRING_OPTS },
  },
  exit: {
    opacity: 0, y: prefersReducedMotion ? 0 : -6,
    transition: { duration: 0.15 },
  },
}

/** Steps container: staggered accordion open */
const stepsContainerVariants = {
  hidden: { opacity: 0, height: 0, overflow: 'hidden' },
  visible: {
    height: 'auto', opacity: 1, overflow: 'visible',
    transition: {
      duration: prefersReducedMotion ? 0.1 : 0.28,
      ease: APPLE_EASE,
      staggerChildren: prefersReducedMotion ? 0 : 0.055,
      when: 'beforeChildren',
    },
  },
  exit: {
    height: 0, opacity: 0, overflow: 'hidden',
    transition: { duration: prefersReducedMotion ? 0.1 : 0.2, ease: APPLE_EASE },
  },
}

/** Individual step row: slides in from left (agent-plan subtask style) */
const stepRowVariants = {
  hidden: { opacity: 0, x: prefersReducedMotion ? 0 : -10 },
  visible: {
    opacity: 1, x: 0,
    transition: { ...SPRING_OPTS },
  },
  exit: {
    opacity: 0, x: prefersReducedMotion ? 0 : -10,
    transition: { duration: 0.15 },
  },
}

/** Status badge: bounces on status change (agent-plan statusBadgeVariants) */
const badgeBounceVariants = {
  initial: { scale: 1 },
  animate: {
    scale: prefersReducedMotion ? 1 : [1, 1.12, 0.96, 1],
    transition: {
      duration: 0.38,
      ease: [0.34, 1.56, 0.64, 1], // springy bounce easing
    },
  },
}

/** Status icon: rotate + scale animate (agent-plan icon transition) */
const iconTransitionProps = {
  initial: { opacity: 0, scale: 0.7, rotate: prefersReducedMotion ? 0 : -12 },
  animate: { opacity: 1, scale: 1, rotate: 0 },
  exit:    { opacity: 0, scale: 0.7, rotate: prefersReducedMotion ? 0 : 12 },
  transition: { duration: 0.2, ease: APPLE_EASE },
}

// ── Status Icon (SVG, no dependency) ──────────────────────────────────────────
function StatusIcon({ status, size = 14 }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.missing
  const s = size

  const icons = {
    complete: (
      // CheckCircle
      <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={cfg.dot} strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round">
        <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
        <polyline points="22 4 12 14.01 9 11.01"/>
      </svg>
    ),
    partial: (
      // CircleAlert
      <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={cfg.dot} strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10"/>
        <line x1="12" y1="8" x2="12" y2="12"/>
        <line x1="12" y1="16" x2="12.01" y2="16"/>
      </svg>
    ),
    missing: (
      // CircleX
      <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={cfg.dot} strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10"/>
        <line x1="15" y1="9" x2="9" y2="15"/>
        <line x1="9" y1="9" x2="15" y2="15"/>
      </svg>
    ),
  }

  return (
    <AnimatePresence mode="wait">
      <motion.div key={status} {...iconTransitionProps} style={{ display: 'flex', flexShrink: 0 }}>
        {icons[status] || icons.missing}
      </motion.div>
    </AnimatePresence>
  )
}

// ── Status Badge with bounce animation ───────────────────────────────────────
function StatusBadge({ status }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.missing
  return (
    <motion.span
      key={status}
      variants={badgeBounceVariants}
      initial="initial"
      animate="animate"
      style={{
        fontSize: 9,
        fontWeight: 800,
        fontFamily: 'JetBrains Mono, monospace',
        letterSpacing: '0.08em',
        color: cfg.color,
        background: cfg.bg,
        border: `1px solid ${cfg.color}33`,
        padding: '2px 7px',
        borderRadius: 4,
        display: 'inline-block',
      }}
    >
      {cfg.label}
    </motion.span>
  )
}

// ── Validation score pill ─────────────────────────────────────────────────────
function ScorePill({ score, hallucination_risk }) {
  const riskColor = {
    low:     'var(--success, #10b981)',
    medium:  'var(--warning, #f59e0b)',
    high:    'var(--danger, #ef4444)',
    unknown: 'var(--text-muted)',
  }[hallucination_risk || 'unknown']

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--text-muted)' }}>
      <span>Score</span>
      <span style={{
        fontFamily: 'JetBrains Mono, monospace',
        fontWeight: 700,
        fontSize: 13,
        color: score >= 70 ? 'var(--success)' : score >= 40 ? 'var(--warning)' : 'var(--danger)',
      }}>
        {score ?? '—'}
      </span>
      <span style={{
        fontSize: 9, letterSpacing: '0.06em', fontWeight: 700,
        color: riskColor, textTransform: 'uppercase',
        fontFamily: 'JetBrains Mono, monospace',
      }}>
        {hallucination_risk || 'unknown'} risk
      </span>
    </div>
  )
}

// ── Individual step row ───────────────────────────────────────────────────────
function StepRow({ step, status }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.missing
  return (
    <motion.div
      variants={stepRowVariants}
      layout
      style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '4px 0', fontSize: 12, color: 'var(--text-secondary)',
      }}
    >
      <StatusIcon status={status} size={13} />
      <span style={{ flex: 1 }}>{step}</span>
      <span style={{
        fontSize: 9, fontFamily: 'JetBrains Mono', fontWeight: 700,
        color: cfg.color, textTransform: 'uppercase',
      }}>
        {status}
      </span>
    </motion.div>
  )
}

// ── Expanded detail section ───────────────────────────────────────────────────
function SectionDetail({ sectionData, sectionId }) {
  const validation = sectionData?.validation || {}
  const trace = sectionData?.trace || {}
  const missing = sectionData?.missing_elements || []
  const sources = sectionData?.source_documents || sectionData?.sources || []
  const status = sectionData?.status || 'missing'

  const getStepStatus = (step) => {
    if (status === 'missing' && step !== 'Load') return 'missing'
    if (step === 'Validate') {
      if (!sectionData?.generated_text && !sectionData?.content) return 'missing'
      return validation.passed ? 'complete' : 'partial'
    }
    if (step === 'Generate') return status
    if (step === 'Map') return sources.length > 0 ? 'complete' : 'missing'
    return 'complete'
  }

  return (
    <motion.div
      variants={stepsContainerVariants}
      initial="hidden"
      animate="visible"
      exit="exit"
      layout
      style={{ overflow: 'hidden' }}
    >
      <div style={{
        borderTop: '1px solid var(--border-default)',
        padding: '10px 14px 14px 14px',
      }}>
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: 12,
        }}>
          {/* Steps column with vertical dashed line (agent-plan style) */}
          <div style={{ position: 'relative' }}>
            <div style={{
              fontSize: 10, fontWeight: 700, color: 'var(--text-muted)',
              textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8,
            }}>
              Pipeline Steps
            </div>
            {/* Vertical dashed connector line — agent-plan pattern */}
            <div style={{
              position: 'absolute',
              top: 30, bottom: 4,
              left: 6,
              borderLeft: '2px dashed rgba(255,255,255,0.1)',
            }} />
            <div style={{ paddingLeft: 4 }}>
              {PIPELINE_STEPS.map((step) => (
                <StepRow key={step} step={step} status={getStepStatus(step)} />
              ))}
            </div>
          </div>

          {/* Sources */}
          <div>
            <div style={{
              fontSize: 10, fontWeight: 700, color: 'var(--text-muted)',
              textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8,
            }}>
              Source Documents ({sources.length})
            </div>
            {sources.length === 0 ? (
              <motion.div
                initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                style={{ fontSize: 11, color: 'var(--danger)', fontStyle: 'italic' }}
              >
                No source evidence matched.
              </motion.div>
            ) : (
              sources.map((s, i) => (
                <motion.div
                  key={i}
                  variants={stepRowVariants}
                  style={{ fontSize: 11, color: 'var(--text-secondary)', padding: '2px 0', display: 'flex', alignItems: 'center', gap: 6 }}
                >
                  <span style={{ color: 'var(--accent)', fontSize: 10 }}>▸</span>
                  <span style={{ fontFamily: 'JetBrains Mono', wordBreak: 'break-all' }}>{s}</span>
                </motion.div>
              ))
            )}
          </div>

          {/* Missing elements */}
          {missing.length > 0 && (
            <div>
              <div style={{
                fontSize: 10, fontWeight: 700, color: 'var(--warning, #f59e0b)',
                textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8,
              }}>
                Missing ({missing.length})
              </div>
              {missing.map((el, i) => (
                <motion.div
                  key={i}
                  variants={stepRowVariants}
                  style={{ fontSize: 11, color: 'var(--text-secondary)', padding: '2px 0', display: 'flex', gap: 6, alignItems: 'flex-start' }}
                >
                  <span style={{ color: 'var(--warning)', flexShrink: 0, marginTop: 1 }}>⚠</span>
                  {el}
                </motion.div>
              ))}
            </div>
          )}

          {/* Trace summary */}
          {(trace.mapping_summary || trace.transformation_summary) && (
            <div>
              <div style={{
                fontSize: 10, fontWeight: 700, color: 'var(--text-muted)',
                textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8,
              }}>
                Trace
              </div>
              {trace.mapping_summary && (
                <motion.div variants={stepRowVariants} style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 4 }}>
                  <span style={{ color: 'var(--accent)', fontWeight: 700 }}>Mapping: </span>
                  {trace.mapping_summary}
                </motion.div>
              )}
              {trace.transformation_summary && (
                <motion.div variants={stepRowVariants} style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
                  <span style={{ color: 'var(--accent)', fontWeight: 700 }}>Transform: </span>
                  {trace.transformation_summary}
                </motion.div>
              )}
            </div>
          )}

          {/* Validation warnings */}
          {(validation.warnings?.length > 0 || validation.errors?.length > 0) && (
            <div style={{ gridColumn: '1 / -1' }}>
              <div style={{
                fontSize: 10, fontWeight: 700, color: 'var(--text-muted)',
                textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8,
              }}>
                Validation Findings
              </div>
              {[...(validation.errors || []), ...(validation.warnings || [])].slice(0, 5).map((msg, i) => (
                <motion.div
                  key={i}
                  variants={stepRowVariants}
                  style={{
                    fontSize: 11, padding: '2px 0',
                    display: 'flex', gap: 6, alignItems: 'flex-start',
                    color: i < (validation.errors?.length || 0) ? 'var(--danger)' : 'var(--warning)',
                  }}
                >
                  <span style={{ flexShrink: 0, marginTop: 1 }}>
                    {i < (validation.errors?.length || 0) ? '✕' : '⚠'}
                  </span>
                  {msg}
                </motion.div>
              ))}
            </div>
          )}
        </div>
      </div>
    </motion.div>
  )
}

// ── Section row ───────────────────────────────────────────────────────────────
function SectionRow({ sectionId, sectionData, sectionMeta, isExpanded, onToggle }) {
  const status = sectionData?.status || 'missing'
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.missing
  const validation = sectionData?.validation || {}

  return (
    <motion.div
      variants={sectionVariants}
      layout
      style={{
        background: 'var(--bg-surface)',
        border: `1px solid ${isExpanded ? cfg.color + '55' : 'var(--border-default)'}`,
        borderRadius: 'var(--radius, 8px)',
        marginBottom: 8,
        overflow: 'hidden',
        transition: 'border-color 0.25s',
      }}
    >
      {/* ── Row header ── */}
      <motion.div
        onClick={onToggle}
        whileHover={prefersReducedMotion ? {} : {
          backgroundColor: 'rgba(255,255,255,0.03)',
          transition: { duration: 0.18 },
        }}
        style={{
          display: 'flex', alignItems: 'center', gap: 12,
          padding: '10px 14px', cursor: 'pointer', userSelect: 'none',
        }}
        layout
      >
        {/* Animated status icon (agent-plan icon transition) */}
        <motion.div
          whileTap={prefersReducedMotion ? {} : { scale: 0.88 }}
          whileHover={prefersReducedMotion ? {} : { scale: 1.1 }}
          style={{ flexShrink: 0 }}
        >
          <StatusIcon status={status} size={18} />
        </motion.div>

        {/* Section identity */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 3 }}>
            <span style={{
              fontFamily: 'JetBrains Mono, monospace', fontSize: 10,
              color: 'var(--accent)', fontWeight: 700,
            }}>
              {sectionMeta?.number || sectionId}
            </span>
            <span style={{
              fontSize: 13, fontWeight: 600, color: 'var(--text-primary)',
              whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
            }}>
              {sectionMeta?.name || sectionData?.section_name || sectionId}
            </span>
          </div>

          {/* Pipeline step dots mini-bar */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
            {PIPELINE_STEPS.map((step, i) => {
              const st = i === 0 ? 'complete'
                : i === 4 ? (validation.passed ? 'complete' : status === 'missing' ? 'missing' : 'partial')
                : status === 'missing' && i > 0 ? 'missing' : status
              const dotColor = STATUS_CONFIG[st]?.dot || '#444'
              return (
                <span key={step} title={`${step}: ${st}`} style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                  <span style={{
                    display: 'inline-block', width: 6, height: 6,
                    borderRadius: '50%', background: dotColor, flexShrink: 0,
                  }} />
                  {i < PIPELINE_STEPS.length - 1 && (
                    <span style={{ display: 'inline-block', width: 8, height: 1, background: dotColor + '55' }} />
                  )}
                </span>
              )
            })}
            <span style={{ fontSize: 9, color: 'var(--text-muted)', marginLeft: 4, fontFamily: 'JetBrains Mono' }}>
              {PIPELINE_STEPS.join(' → ')}
            </span>
          </div>
        </div>

        {/* Right side */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
          {validation.score !== undefined && (
            <ScorePill score={validation.score} hallucination_risk={validation.hallucination_risk} />
          )}
          <StatusBadge status={status} />
          <motion.svg
            width={14} height={14} viewBox="0 0 24 24" fill="none"
            stroke="var(--text-muted)" strokeWidth={2}
            animate={{ rotate: isExpanded ? 180 : 0 }}
            transition={{ duration: 0.22, ease: APPLE_EASE }}
          >
            <polyline points="6 9 12 15 18 9" />
          </motion.svg>
        </div>
      </motion.div>

      {/* ── Expanded detail panel ── */}
      <AnimatePresence mode="wait">
        {isExpanded && (
          <SectionDetail
            key={`detail-${sectionId}`}
            sectionData={sectionData}
            sectionId={sectionId}
          />
        )}
      </AnimatePresence>
    </motion.div>
  )
}

// ── Main Component ────────────────────────────────────────────────────────────
/**
 * PipelineVisualizer
 * Props:
 *   sections     — object keyed by section_id → SectionResult dict
 *   sectionsMeta — SECTIONS config from App (name, number)
 *   isLoading    — bool
 */
export default function PipelineVisualizer({ sections, sectionsMeta = {}, isLoading = false }) {
  const [expandedId, setExpandedId] = useState(null)
  const sectionIds = Object.keys(sections || {})

  if (isLoading) {
    return (
      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 1 }}
        style={{ padding: 20, color: 'var(--text-muted)', fontSize: 12, textAlign: 'center', fontFamily: 'JetBrains Mono' }}
      >
        Awaiting pipeline output…
      </motion.div>
    )
  }

  if (!sectionIds.length) {
    return (
      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 1 }}
        style={{ padding: 16, color: 'var(--text-muted)', fontSize: 12, textAlign: 'center',
          border: '1px dashed var(--border-default)', borderRadius: 'var(--radius)', }}
      >
        No sections generated yet.
      </motion.div>
    )
  }

  const complete = sectionIds.filter(id => sections[id]?.status === 'complete').length
  const partial  = sectionIds.filter(id => sections[id]?.status === 'partial').length
  const missing  = sectionIds.filter(id => sections[id]?.status === 'missing').length

  return (
    <LayoutGroup>
      {/* Summary header */}
      <motion.div
        layout
        initial={{ opacity: 0, y: prefersReducedMotion ? 0 : -8 }}
        animate={{ opacity: 1, y: 0, transition: { duration: 0.3, ease: APPLE_EASE } }}
        style={{
          display: 'flex', gap: 16, marginBottom: 14,
          padding: '10px 14px',
          background: 'var(--bg-surface)',
          borderRadius: 'var(--radius)',
          border: '1px solid var(--border-default)',
          fontSize: 12,
        }}
      >
        <span style={{ color: 'var(--text-muted)', fontWeight: 600 }}>Pipeline Summary</span>
        <span style={{ color: STATUS_CONFIG.complete.color }}><strong>{complete}</strong> complete</span>
        <span style={{ color: STATUS_CONFIG.partial.color }}><strong>{partial}</strong> partial</span>
        <span style={{ color: STATUS_CONFIG.missing.color }}><strong>{missing}</strong> missing</span>
        <span style={{ color: 'var(--text-muted)', marginLeft: 'auto', fontFamily: 'JetBrains Mono', fontSize: 10 }}>
          {sectionIds.length} sections
        </span>
      </motion.div>

      {/* Section rows */}
      <motion.ul
        layout
        initial="hidden"
        animate="visible"
        variants={{ visible: { transition: { staggerChildren: prefersReducedMotion ? 0 : 0.06 } } }}
        style={{ listStyle: 'none', margin: 0, padding: 0 }}
      >
        {sectionIds.map(id => (
          <motion.li key={id} variants={sectionVariants} layout>
            <SectionRow
              sectionId={id}
              sectionData={sections[id]}
              sectionMeta={sectionsMeta[id]}
              isExpanded={expandedId === id}
              onToggle={() => setExpandedId(expandedId === id ? null : id)}
            />
          </motion.li>
        ))}
      </motion.ul>
    </LayoutGroup>
  )
}
