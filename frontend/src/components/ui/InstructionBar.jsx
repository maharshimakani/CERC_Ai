/**
 * InstructionBar.jsx — Upgraded with v0-ai-chat.tsx patterns
 * ─────────────────────────────────────────────────────────────────────
 * Effects integrated from v0-ai-chat.tsx:
 *   ✔ useAutoResizeTextarea hook (JS port — no TS needed)
 *   ✔ Smooth animated focus ring on container (framer-motion border glow)
 *   ✔ Send button state transition (bg/color smooth swap on value change)
 *   ✔ Preset pills with staggered appear + hover lift (agent-plan tool badges)
 *   ✔ prefers-reduced-motion respected
 *
 * Regulated constraints maintained:
 *   ✔ NOT a chat — no history, no assistant persona
 *   ✔ Disabled when: no docs / no sections / pipeline running
 *   ✔ Constraint-only presets (past tense, numeric detail, etc.)
 */

import { useState, useRef, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

// ── prefers-reduced-motion ────────────────────────────────────────────────────
const prefersReducedMotion =
  typeof window !== 'undefined' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches

const APPLE_EASE = [0.2, 0.65, 0.3, 0.9]

// ── useAutoResizeTextarea (ported from v0-ai-chat.tsx) ────────────────────────
function useAutoResizeTextarea({ minHeight, maxHeight }) {
  const textareaRef = useRef(null)

  const adjustHeight = useCallback((reset) => {
    const textarea = textareaRef.current
    if (!textarea) return
    if (reset) {
      textarea.style.height = `${minHeight}px`
      return
    }
    // Shrink first to get accurate scrollHeight
    textarea.style.height = `${minHeight}px`
    const newHeight = Math.max(minHeight, Math.min(textarea.scrollHeight, maxHeight ?? Infinity))
    textarea.style.height = `${newHeight}px`
  }, [minHeight, maxHeight])

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = `${minHeight}px`
    }
  }, [minHeight])

  useEffect(() => {
    const handleResize = () => adjustHeight()
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [adjustHeight])

  return { textareaRef, adjustHeight }
}

// ── Constrained preset definitions (not chat prompts) ─────────────────────────
const CONSTRAINT_PRESETS = [
  { label: 'Past tense only',       value: 'Enforce past tense throughout. Flag any present-tense constructs.' },
  { label: 'No abbreviations',      value: 'Do not use abbreviations. Spell out all clinical terms in full.' },
  { label: 'Verbose numerics',      value: 'Include all numeric data points, dates, and statistical values explicitly.' },
  { label: 'Regulatory tone',       value: 'Use formal regulatory language only. No colloquial expressions.' },
  { label: 'ICH E3 compliant',      value: 'Structure output strictly to ICH E3 section guidelines.' },
]

// ── Preset pill (agent-plan tool badge style) ─────────────────────────────────
function PresetPill({ preset, onClick, index }) {
  return (
    <motion.button
      onClick={onClick}
      initial={{ opacity: 0, y: prefersReducedMotion ? 0 : -5 }}
      animate={{
        opacity: 1, y: 0,
        transition: { duration: 0.2, delay: prefersReducedMotion ? 0 : index * 0.05, ease: APPLE_EASE },
      }}
      whileHover={prefersReducedMotion ? {} : {
        y: -2,
        backgroundColor: 'var(--bg-interactive)',
        borderColor: 'var(--accent)',
        color: 'var(--text-primary)',
        transition: { duration: 0.18 },
      }}
      whileTap={prefersReducedMotion ? {} : { scale: 0.96 }}
      style={{
        fontSize: 10,
        padding: '3px 10px',
        borderRadius: 5,
        background: 'var(--bg-interactive)',
        border: '1px solid var(--border-default)',
        color: 'var(--text-secondary)',
        cursor: 'pointer',
        fontFamily: 'JetBrains Mono, monospace',
        letterSpacing: '0.02em',
        lineHeight: 1.6,
      }}
    >
      {preset.label}
    </motion.button>
  )
}

// ── Main Component ────────────────────────────────────────────────────────────
export default function InstructionBar({ onSubmit, disabled, disabledReason = '' }) {
  const [value, setValue] = useState('')
  const [showPresets, setShowPresets] = useState(false)
  const [isFocused, setIsFocused] = useState(false)

  const { textareaRef, adjustHeight } = useAutoResizeTextarea({ minHeight: 40, maxHeight: 140 })

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const handleSubmit = () => {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSubmit(trimmed)
    setValue('')
    adjustHeight(true)
  }

  const canSubmit = value.trim().length > 0 && !disabled

  return (
    <div>
      {/* ── Container with animated focus border (v0-ai-chat style) ── */}
      <motion.div
        animate={{
          borderColor: disabled
            ? 'var(--border-default)'
            : isFocused
              ? 'rgba(99,102,241,0.55)'    // accent glow when focused
              : 'var(--border-default)',
          boxShadow: !disabled && isFocused && !prefersReducedMotion
            ? '0 0 0 3px rgba(99,102,241,0.12)'
            : '0 0 0 0px rgba(99,102,241,0)',
        }}
        transition={{ duration: 0.22, ease: APPLE_EASE }}
        style={{
          background: 'var(--bg-surface)',
          border: '1px solid var(--border-default)',
          borderRadius: 'var(--radius, 8px)',
          padding: '10px 12px',
          opacity: disabled ? 0.6 : 1,
          transition: 'opacity 0.2s',
        }}
      >
        {/* Header row */}
        <div style={{
          display: 'flex', alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 8,
        }}>
          <div style={{
            fontSize: 10, fontWeight: 800,
            fontFamily: 'JetBrains Mono, monospace',
            color: 'var(--text-muted)',
            textTransform: 'uppercase', letterSpacing: '0.08em',
            display: 'flex', alignItems: 'center', gap: 6,
          }}>
            <span style={{ color: 'var(--accent)' }}>//</span>
            Generation Constraints
            <AnimatePresence>
              {disabled && disabledReason && (
                <motion.span
                  initial={{ opacity: 0, x: -4 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -4 }}
                  transition={{ duration: 0.18 }}
                  style={{ color: 'var(--warning, #f59e0b)', fontSize: 9, fontWeight: 600, marginLeft: 4 }}
                >
                  — {disabledReason}
                </motion.span>
              )}
            </AnimatePresence>
          </div>

          {/* Presets toggle */}
          <motion.button
            disabled={disabled}
            onClick={() => setShowPresets(p => !p)}
            whileHover={disabled || prefersReducedMotion ? {} : { color: 'var(--accent)' }}
            whileTap={prefersReducedMotion ? {} : { scale: 0.95 }}
            style={{
              fontSize: 10, fontFamily: 'JetBrains Mono',
              color: disabled ? 'var(--text-muted)' : 'var(--accent)',
              background: 'none', border: 'none',
              cursor: disabled ? 'not-allowed' : 'pointer',
              padding: '2px 6px', borderRadius: 4,
            }}
          >
            {showPresets ? '▾ PRESETS' : '▸ PRESETS'}
          </motion.button>
        </div>

        {/* Preset pills — staggered appear (agent-plan tool badge pattern) */}
        <AnimatePresence>
          {showPresets && !disabled && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto', transition: { duration: 0.22, ease: APPLE_EASE } }}
              exit={{ opacity: 0, height: 0, transition: { duration: 0.15 } }}
              style={{ overflow: 'hidden', marginBottom: 8 }}
            >
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, paddingTop: 2 }}>
                {CONSTRAINT_PRESETS.map((preset, i) => (
                  <PresetPill
                    key={preset.label}
                    preset={preset}
                    index={i}
                    onClick={() => {
                      setValue(preset.value)
                      adjustHeight()
                      setShowPresets(false)
                      textareaRef.current?.focus()
                    }}
                  />
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Auto-resize textarea (v0-ai-chat pattern) */}
        <div style={{ overflowY: 'auto' }}>
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => {
              setValue(e.target.value)
              adjustHeight()
            }}
            onKeyDown={handleKeyDown}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
            disabled={disabled}
            placeholder={
              disabled
                ? disabledReason || 'Upload documents and select sections to enable.'
                : 'Define generation constraints… e.g. "Enforce past tense. Include all numeric values."'
            }
            style={{
              width: '100%',
              background: 'transparent',
              color: 'var(--text-primary)',
              border: 'none',
              outline: 'none',
              resize: 'none',
              fontSize: 12,
              fontFamily: 'var(--font-body, Inter, sans-serif)',
              lineHeight: 1.6,
              overflow: 'hidden',
              minHeight: 40,
              maxHeight: 140,
              caretColor: 'var(--accent)',
              cursor: disabled ? 'not-allowed' : 'text',
            }}
          />
        </div>

        {/* Footer row — v0-ai-chat bottom bar pattern */}
        <div style={{
          display: 'flex', alignItems: 'center',
          justifyContent: 'space-between',
          marginTop: 8, paddingTop: 8,
          borderTop: '1px solid var(--border-default)',
        }}>
          <span style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'JetBrains Mono' }}>
            {value.trim().length > 0
              ? `${value.trim().length} chars · Ctrl+Enter to apply`
              : 'Constraints apply to next generation only'}
          </span>

          {/* Send button — v0-ai-chat style: white bg + black icon when active */}
          <motion.button
            disabled={!canSubmit}
            onClick={handleSubmit}
            animate={{
              background: canSubmit ? '#ffffff' : 'var(--bg-interactive)',
              color: canSubmit ? '#000000' : 'var(--text-muted)',
              opacity: canSubmit ? 1 : 0.45,
            }}
            whileHover={canSubmit && !prefersReducedMotion ? { scale: 1.06 } : {}}
            whileTap={canSubmit && !prefersReducedMotion ? { scale: 0.93 } : {}}
            transition={{ duration: 0.18, ease: APPLE_EASE }}
            title={canSubmit ? 'Apply constraint (Ctrl+Enter)' : 'Enter a constraint first'}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '5px 12px', borderRadius: 6,
              fontSize: 11, fontWeight: 700, fontFamily: 'JetBrains Mono',
              cursor: canSubmit ? 'pointer' : 'not-allowed',
              border: '1px solid var(--border-default)',
            }}
          >
            {/* Arrow up icon (v0-ai-chat ArrowUpIcon) */}
            <motion.svg
              width={12} height={12} viewBox="0 0 24 24"
              fill="none" stroke="currentColor" strokeWidth={2.5}
              animate={{ y: canSubmit && !prefersReducedMotion ? [0, -1, 0] : 0 }}
              transition={{ duration: 0.4, repeat: canSubmit ? Infinity : 0, repeatDelay: 2 }}
            >
              <line x1="12" y1="19" x2="12" y2="5" />
              <polyline points="5 12 12 5 19 12" />
            </motion.svg>
            APPLY
          </motion.button>
        </div>
      </motion.div>

      {/* Character count micro indicator (animated) */}
      <AnimatePresence>
        {value.length > 100 && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.18 }}
            style={{
              marginTop: 4, fontSize: 9, color: 'var(--text-muted)',
              fontFamily: 'JetBrains Mono', textAlign: 'right',
            }}
          >
            {value.length} / 500 chars
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
