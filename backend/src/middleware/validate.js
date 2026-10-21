'use strict';

const { validationResult } = require('express-validator');
const ApiError = require('../utils/ApiError');

function validate(chains) {
  return async function validationMiddleware(req, res, next) {
    try {
      await Promise.all(chains.map((chain) => chain.run(req)));
      const result = validationResult(req);
      if (result.isEmpty()) return next();

      const details = result.array({ onlyFirstError: true }).map((e) => ({
        field: e.path ?? e.param,
        message: e.msg,
      }));
      return next(ApiError.validation('Invalid request payload', details));
    } catch (err) {
      return next(err);
    }
  };
}

module.exports = validate;
