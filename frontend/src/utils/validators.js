import { required as _required, email as _email, minLength as _minLength, maxLength as _maxLength, minValue as _minValue, maxValue as _maxValue, numeric as _numeric, integer as _integer, url as _url, helpers } from '@vuelidate/validators'

export const required = helpers.withMessage('This field is required', _required)

export const email = helpers.withMessage('Please enter a valid email address', _email)

export const minLength = (min) => helpers.withMessage(`Must be at least ${min} characters long`, _minLength(min))

export const maxLength = (max) => helpers.withMessage(`Must be no more than ${max} characters long`, _maxLength(max))

export const minValue = (min) => helpers.withMessage(`Must be at least ${min}`, _minValue(min))

export const maxValue = (max) => helpers.withMessage(`Must be no more than ${max}`, _maxValue(max))

export const numeric = helpers.withMessage('Must be a valid number', _numeric)

export const integer = helpers.withMessage('Must be a whole number', _integer)

export const url = helpers.withMessage('Please enter a valid URL', _url)

export const pattern = (regex, message = 'Invalid format') => helpers.withMessage(message, helpers.regex(regex))

const packagePatterns = {
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

export const packageName = (ecosystem) => helpers.withMessage(
  `Invalid package name format for ${ecosystem}`,
  (value) => {
    if (!value) return true
    const ecosystemPattern = packagePatterns[ecosystem?.toLowerCase()]
    if (!ecosystemPattern) return true
    return ecosystemPattern.test(value)
  }
)

export const versionSpec = helpers.withMessage('Invalid version specification', (value) => {
  if (!value) return true

  const versionPatterns = [
    /^\d+(\.\d+)*$/,
    /^[><=~^!]*\d+(\.\d+)*$/,
    /^\d+(\.\d+)*(\s*,\s*[><=~^!]*\d+(\.\d+)*)*$/,
    /^\*$/,
    /^latest$/
  ]

  return versionPatterns.some(pattern => pattern.test(value.trim()))
})

export const systemSpec = helpers.withMessage(
  'Invalid system specification format. Use: key=value,key=value',
  (value) => {
    if (!value) return true
    return /^[a-zA-Z_][a-zA-Z0-9_]*=[^,=]+(,[a-zA-Z_][a-zA-Z0-9_]*=[^,=]+)*$/.test(value)
  }
)

export const filename = (value) => {
  if (!value) return true

  if (/[<>:"/\\|?*]/.test(value)) {
    return 'Filename contains invalid characters'
  }

  if (value.length > 255) {
    return 'Filename is too long'
  }

  return true
}

export const apiKey = (value) => {
  if (!value) return true

  if (!/^[a-zA-Z0-9_-]+$/.test(value) || value.length < 20) {
    return 'Invalid API key format'
  }
  return true
}

export const password = (value) => {
  if (!value) return true

  const errors = []

  if (value.length < 8) {
    errors.push('at least 8 characters')
  }

  if (!helpers.regex(/[a-z]/)(value)) {
    errors.push('one lowercase letter')
  }

  if (!helpers.regex(/[A-Z]/)(value)) {
    errors.push('one uppercase letter')
  }

  if (!helpers.regex(/\d/)(value)) {
    errors.push('one number')
  }

  if (!helpers.regex(/[!@#$%^&*(),.?":{}|<>]/)(value)) {
    errors.push('one special character')
  }

  if (errors.length > 0) {
    return `Password must contain ${errors.join(', ')}`
  }

  return true
}

export const confirmPassword = (originalPassword) => {
  const validator = (value, siblings) => {
    if (!value) return true
    return value === (siblings?.password ?? originalPassword)
  }
  return helpers.withMessage('Passwords do not match', validator)
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
      return extension === type.slice(1)
    } else {
      return fileType.includes(type)
    }
  })

  if (!isTypeAllowed) {
    return `File type not allowed. Allowed types: ${allowedTypes.join(', ')}`
  }
  return true
}

export const validateField = (value, validators) => {
  for (const validator of validators) {
    const result = validator(value)
    if (result !== true) {
      return result
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

export const createRealtimeValidator = (validationRules, debounceMs = 300) => {
  let timeouts = {}

  return (field, value, callback) => {
    if (timeouts[field]) {
      clearTimeout(timeouts[field])
    }

    timeouts[field] = setTimeout(async () => {
      const rules = validationRules[field] || []

      try {
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
  packageName,
  versionSpec,
  systemSpec,
  filename,
  apiKey,
  password,
  confirmPassword,
  fileSize,
  fileType,
  uniqueUsername,
  uniqueEmail,
  packageExists,
  validateField,
  validateForm,
  createVuelidateRules,
  createRealtimeValidator,
  authValidation,
  packageSearchValidation,
  systemRequirementValidation,
  exportValidation
}
