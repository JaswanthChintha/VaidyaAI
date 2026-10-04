'use strict';

const express = require('express');

const authController = require('../controllers/authController');
const validate = require('../middleware/validate');
const { protect, restrictTo } = require('../middleware/auth');
const { authLimiter, loginLimiter } = require('../middleware/rateLimiter');
const { ROLES } = require('../utils/roles');
const {
  registerValidator,
  loginValidator,
  refreshValidator,
  logoutValidator,
  changePasswordValidator,
  deleteAccountValidator,
} = require('../middleware/authValidators');

const router = express.Router();

// General throttle across the whole auth surface.
router.use(authLimiter);

router.post('/register', loginLimiter, validate(registerValidator), authController.register);
router.post('/login', loginLimiter, validate(loginValidator), authController.login);
router.post('/refresh', validate(refreshValidator), authController.refresh);
router.post('/logout', validate(logoutValidator), authController.logout);

router.get('/me', protect, authController.getMe);

// Both re-check the current password, so both take the login limiter: they
// are as good a password-guessing oracle as /login is.
router.post(
  '/change-password',
  protect,
  loginLimiter,
  validate(changePasswordValidator),
  authController.changePassword
);
router.delete('/me', protect, loginLimiter, validate(deleteAccountValidator), authController.deleteAccount);

// Authorization demo//guard: admins only.
router.get('/admin/users', protect, restrictTo(ROLES.ADMIN), authController.listUsers);

module.exports = router;
