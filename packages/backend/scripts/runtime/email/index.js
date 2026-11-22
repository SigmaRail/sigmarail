let _renderEmail;

try {
  const { renderEmail } = require('./renderer/index.umd');
  _renderEmail = renderEmail;
} catch {
  // Never turn renderer failures into emails. In debug mode the old fallback
  // exposed serialized payloads, including account activation tokens.
  _renderEmail = () => {
    throw Error(
      'Email renderer script is missing. Build webapp-emails and copy its renderer into scripts/runtime/email/renderer.',
    );
  };
}

module.exports = { renderEmail: _renderEmail };
