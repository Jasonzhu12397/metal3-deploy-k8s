import { describe, it, expect } from 'vitest'
import { extractErrorMessage, ApiError } from '../../lib/api'

// This function is the site of a real production bug: it used to do
// `String(body.detail)` unconditionally. That's fine when detail is a
// plain string (the common case -- HTTPException(status, "some string")),
// but FastAPI's automatic Pydantic validation errors (422s) return
// `detail` as a LIST of {msg, loc, ...} objects, and JS's default
// Array/Object stringification of that is the literal text
// "[object Object]" -- which is exactly what a user saw on screen when
// creating a docker-provider cluster hit a validation error. This test
// file is what that bug was missing: a permanent, always-run regression
// test, not just a one-off Node script verification during the fix.
describe('extractErrorMessage', () => {
  it('returns a plain string detail directly (the common HTTPException case)', () => {
    expect(extractErrorMessage(409, { detail: "Cluster 'test1' already exists" })).toBe(
      "Cluster 'test1' already exists",
    )
  })

  it('extracts and joins messages from a FastAPI Pydantic validation error array -- never "[object Object]"', () => {
    // The exact shape FastAPI actually returns for a 422, captured from
    // a real request during the bug investigation.
    const realValidationErrorBody = {
      detail: [
        {
          type: 'value_error',
          loc: [],
          msg: "Value error, infrastructure_provider=openstack needs control_plane_flavor and control_plane_image (there's no HardwareAsset to derive a machine spec from for a cloud/VM-based provider)",
          input: {},
          ctx: {},
          url: 'https://errors.pydantic.dev/2.9/v/value_error',
        },
      ],
    }
    const message = extractErrorMessage(422, realValidationErrorBody)
    expect(message).not.toContain('[object Object]')
    expect(message).toBe(
      "Value error, infrastructure_provider=openstack needs control_plane_flavor and control_plane_image (there's no HardwareAsset to derive a machine spec from for a cloud/VM-based provider)",
    )
  })

  it('prefixes the field name when loc is present (field-level validation errors)', () => {
    const fieldError = { detail: [{ loc: ['body', 'name'], msg: 'field required', type: 'missing' }] }
    expect(extractErrorMessage(422, fieldError)).toBe('name: field required')
  })

  it('joins multiple validation errors with a separator', () => {
    const multipleErrors = {
      detail: [
        { loc: ['body', 'name'], msg: 'field required' },
        { loc: ['body', 'control_plane_count'], msg: 'must be a positive integer' },
      ],
    }
    expect(extractErrorMessage(422, multipleErrors)).toBe(
      'name: field required; control_plane_count: must be a positive integer',
    )
  })

  it('falls back to "HTTP {status}" when there is no detail field at all', () => {
    expect(extractErrorMessage(500, {})).toBe('HTTP 500')
  })

  it('falls back to "HTTP {status}" when body is null (e.g. a non-JSON response)', () => {
    expect(extractErrorMessage(500, null)).toBe('HTTP 500')
  })

  it('falls back to "HTTP {status}" when body is not an object at all', () => {
    expect(extractErrorMessage(502, 'Bad Gateway')).toBe('HTTP 502')
  })

  it('JSON-stringifies an unexpected object shape rather than producing "[object Object]"', () => {
    const weirdShape = { detail: { unexpected: 'structure' } }
    const message = extractErrorMessage(500, weirdShape)
    expect(message).not.toBe('[object Object]')
    expect(message).toContain('unexpected')
  })
})

describe('ApiError', () => {
  it('exposes the extracted message via .message, and preserves status/body', () => {
    const err = new ApiError(422, {
      detail: [{ loc: ['body', 'name'], msg: 'field required' }],
    })
    expect(err.message).toBe('name: field required')
    expect(err.status).toBe(422)
    expect(err instanceof Error).toBe(true)
  })
})
