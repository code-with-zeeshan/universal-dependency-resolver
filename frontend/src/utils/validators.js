// frontend/src/utils/validators.js

/**
 * Validation utilities for form inputs
 */

// Basic validation functions
export const required = (value) => {
  if (value === null || value === undefined || value === '') {
    return 'This field is required'
  }
  if (Array.isArray(value) && value.length === 0) {
    return 'This field is required'
  }
  return true
}

export const email = (value) => {
  if (!value) return true // Let required handle empty values
  
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
  if (!emailRegex.test(value)) {
    return 'Please enter a valid email address'
  }
  return true
}

export const minLength = (min) => (value) => {
  if (!value) return true // Let required handle empty values
  
  if (value.length < min) {
    return `Must be at least ${min} characters long`
  }
  return true
}

export const maxLength = (max) => (value) => {
  if (!value) return true
  
  if (value.length > max) {
    return `Must be no more than ${max} characters long`
  }
  return true
}

export const minValue = (min) => (value) => {
  if (value === null || value === undefined || value === '') return true
  
  const numValue = Number(value)
  if (isNaN(numValue) || numValue < min) {
    return `Must be at least ${min}`
  }
  return true
}

export const maxValue = (max) => (value) => {
  if (value === null || value === undefined || value === '') return true
  
  const numValue = Number(value)
  if (isNaN(numValue) || numValue > max) {
    return `Must be no more than ${max}`
  }
  return true
}

export const numeric = (value) => {
  if (!value) return true
  
  if (isNaN(Number(value))) {
    return 'Must be a valid number'
  }
  return true
}

export const integer = (value) => {
  if (!value) return true
  
  const numValue = Number(value)
  if (isNaN(numValue) || !Number.isInteger(numValue)) {
    return 'Must be a whole number'
  }
  return true
}

export const url = (value) => {
  if (!value) return true
  
  try {
    new URL(value)
    return true
  } catch {
    return 'Please enter a valid URL'
  }
}

export const pattern = (regex, message = 'Invalid format') => (value) => {
  if (!value) return true
  
  if (!regex.test(value)) {
    return message
  }
  return true
}

// Package-specific validators
export const packageName = (ecosystem) => (value) => {
  if (!value) return true
  
  const patterns = {
    pypi: /^[a-zA-Z0-9]([a-zA-Z0-9._-])*[a-zA-Z0-9]$/,
    npm: /^(?:@[a-zA-Z0-9-]+\/)?[a-zA-Z0-9-]+$/,
    maven: /^[a-zA-Z0-9._-]+:[a-zA-Z0-9._-]+$/,
    crates: /^[a-zA-Z0-9_-]+$/,
    conda: /^[a-zA-Z0-9_-]+$/,
    gomodules: /^[a-zA-Z0-9._/-]+$/,
    apt: /^[a-z0-9][a-z0-9+.-]+$/,
    apk: /^[a-z0-9][a-z0-9+.-]+$/,
    cocoapods: /^[a-zA-Z0-9_-]+$/,
    rubygems: /^[a-zA-Z0-9][a-zA-Z0-9_-]*$/,
    packagist: /^[a-z0-9]([_.-]?[a-z0-9]+)*\/[a-z0-9]([_.-]?[a-z0-9]+)*$/,
    nuget: /^[a-zA-Z0-9][a-zA-Z0-9._-]*$/,
    homebrew: /^[a-z0-9][a-z0-9+.-]+$/
  }
  
  const ecosystemPattern = patterns[ecosystem?.toLowerCase()]
  if (!ecosystemPattern) {
    return true // Unknown ecosystem, allow any format
  }
  
  if (!ecosystemPattern.test(value)) {
    return `Invalid package name format for ${ecosystem}`
  }
  return true
}

export const versionSpec = (value) => {
  if (!value) return true
  
  // Basic version specification patterns
  const versionPatterns = [
    /^\d+(\.\d+)*$/, // Simple version: 1.2.3
    /^[><=~^!]*\d+(\.\d+)*$/, // With operators: >=1.2.3, ~1.2.0
    /^\d+(\.\d+)*(\s*,\s*[><=~^!]*\d+(\.\d+)*)*$/, // Multiple specs: >=1.0,<2.0
    /^\*$/, // Wildcard
    /^latest$/, // Latest keyword
  ]
  
  const isValid = versionPatterns.some(pattern => pattern.test(value.trim()))
  if (!isValid) {
    return 'Invalid version specification'
  }
  return true
}

export const systemSpec = (value) => {
  if (!value) return true
  
  // System specification format: key=value,key=value
  const specPattern = /^[a-zA-Z_][a-zA-Z0-9_]*=[^,=]+(,[a-zA-Z_][a-zA-Z0-9_]*=[^,=]+)*$/
  if (!specPattern.test(value)) {
    return 'Invalid system specification format. Use: key=value,key=value'
  }
  return true
}

export const filename = (value) => {
  if (!value) return true
  
  // Check for invalid filename characters
  const invalidChars = /[<>:"/\\|?*]/
  if (invalidChars.test(value)) {
    return 'Filename contains invalid characters'
  }
  
  // Check length
  if (value.length > 255) {
    return 'Filename is too long'
  }
  
  return true
}

export const apiKey = (value) => {
  if (!value) return true
  
  // API key format validation
  if (!/^[a-zA-Z0-9_-]+$/.test(value) || value.length < 20) {
    return 'Invalid API key format'
  }
  return true
}

// Composite validators
export const password = (value) => {
  if (!value) return true
  
  const errors = []
  
  if (value.length < 8) {
    errors.push('at least 8 characters')
  }
  
  if (!/[a-z]/.test(value)) {
    errors.push('one lowercase letter')
  }
  
  if (!/[A-Z]/.test(value)) {
    errors.push('one uppercase letter')
  }
  
  if (!/\d/.test(value)) {
    errors.push('one number')
  }
  
  if (!/[!@#$%^&*(),.?":{}|<>]/.test(value)) {
    errors.push('one special character')
  }
  
  if (errors.length > 0) {
    return `Password must contain ${errors.join(', ')}`
  }
  
  return true
}

export const confirmPassword = (originalPassword) => (value) => {
  if (!value) return true
  
  if (value !== originalPassword) {
    return 'Passwords do not match'
  }
  return true
}

export const fileSize = (maxSizeMB) => (file) => {
  if (!file) return true
  
  const maxSizeBytes = maxSizeMB * 1024 * 1024
  if (file.size > maxSizeBytes) {
    return `File size must be less than ${maxSizeMB}MB`
  }
  return true
}

export const fileType = (allowedTypes) => (file) => {
  if (!file) return true
  
  const fileType = file.type || ''
  const fileName = file.name || ''
  const extension = fileName.split('.').pop()?.toLowerCase()
  
  const isTypeAllowed = allowedTypes.some(type => {
    if (type.startsWith('.')) {
      // Extension check
      return extension === type.slice(1)
    } else {
      // MIME type check
      return fileType.includes(type)
    }
  })
  
  if (!isTypeAllowed) {
    return `File type not allowed. Allowed types: ${allowedTypes.join(', ')}`
  }
  return true
}

// Validation utility functions
export const validateField = (value, validators) => {
  for (const validator of validators) {
    const result = validator(value)
    if (result !== true) {
      return result // Return first error message
    }
  }
  return true
}

export const validateForm = (formData, validationRules) => {
  const errors = {}
  let isValid = true
  
  for (const [field, rules] of Object.entries(validationRules)) {
    const fieldValue = formData[field]
    const fieldResult = validateField(fieldValue, rules)
    
    if (fieldResult !== true) {
      errors[field] = fieldResult
      isValid = false
    }
  }
  
  return { isValid, errors }
}

// Async validators
export const uniqueUsername = (checkFunction) => async (value) => {
  if (!value) return true
  
  try {
    const isUnique = await checkFunction(value)
    if (!isUnique) {
      return 'Username is already taken'
    }
    return true
  } catch (error) {
    return 'Unable to verify username availability'
  }
}

export const uniqueEmail = (checkFunction) => async (value) => {
  if (!value) return true
  
  try {
    const isUnique = await checkFunction(value)
    if (!isUnique) {
      return 'Email is already registered'
    }
    return true
  } catch (error) {
    return 'Unable to verify email availability'
  }
}

export const packageExists = (checkFunction) => async (value, ecosystem) => {
  if (!value) return true
  
  try {
    const exists = await checkFunction(value, ecosystem)
    if (!exists) {
      return `Package '${value}' not found in ${ecosystem}`
    }
    return true
  } catch (error) {
    return 'Unable to verify package existence'
  }
}

// Validation presets for common forms
export const authValidation = {
  username: [required, minLength(3), maxLength(50), pattern(/^[a-zA-Z0-9_-]+$/, 'Only letters, numbers, underscores, and hyphens allowed')],
  email: [required, email],
  password: [required, password],
  confirmPassword: (originalPassword) => [required, confirmPassword(originalPassword)]
}

export const packageSearchValidation = {
  query: [required, minLength(2), maxLength(100)],
  ecosystem: [required],
  version: [versionSpec]
}

export const systemRequirementValidation = {
  type: [required],
  specification: [systemSpec]
}

export const exportValidation = {
  format: [required],
  filename: [filename],
  packages: [required]
}

// Vue.js integration helper
export const createVuelidateRules = (validationRules) => {
  const rules = {}
  
  for (const [field, validators] of Object.entries(validationRules)) {
    rules[field] = {}
    
    validators.forEach((validator, index) => {
      const ruleName = validator.name || `rule${index}`
      rules[field][ruleName] = validator
    })
  }
  
  return rules
}

// Real-time validation helper
export const createRealtimeValidator = (validationRules, debounceMs = 300) => {
  let timeouts = {}
  
  return (field, value, callback) => {
    // Clear existing timeout for this field
    if (timeouts[field]) {
      clearTimeout(timeouts[field])
    }
    
    // Set new timeout
    timeouts[field] = setTimeout(async () => {
      const rules = validationRules[field] || []
      
      try {
        // Handle async validators
        const results = await Promise.all(
          rules.map(rule => Promise.resolve(rule(value)))
        )
        
        const error = results.find(result => result !== true)
        callback(field, error || null)
      } catch (err) {
        callback(field, 'Validation error occurred')
      }
    }, debounceMs)
  }
}

export default {
  // Basic validators
  required,
  email,
  minLength,
  maxLength,
  minValue,
  maxValue,
  numeric,
  integer,
  url,
  pattern,
  
  // Package-specific validators
  packageName,
  versionSpec,
  systemSpec,
  filename,
  apiKey,
  
  // Composite validators
  password,
  confirmPassword,
  fileSize,
  fileType,
  
  // Async validators
  uniqueUsername,
  uniqueEmail,
  packageExists,
  
  // Validation utilities
  validateField,
  validateForm,
  createVuelidateRules,
  createRealtimeValidator,
  
  // Presets
  authValidation,
  packageSearchValidation,
  systemRequirementValidation,
  exportValidation
}