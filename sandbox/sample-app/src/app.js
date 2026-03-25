// sample-app: minimal hello-world module
// Used as a test target for ai-dev-flow smoke tests.

/**
 * Returns a greeting string for the given name.
 * @param {string} name
 * @returns {string}
 */
function greet(name) {
  return `Hello, ${name}!`;
}

// TODO: add a syncData(source, target) function that copies records
// from source to target with retry logic and idempotency checks.
// This is intentionally left unimplemented so `ai feature "sample sync"`
// has something realistic to work with.

module.exports = { greet };
