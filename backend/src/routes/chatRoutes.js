'use strict';

const express = require('express');

const chatController = require('../controllers/chatController');
const validate = require('../middleware/validate');
const { protect } = require('../middleware/auth');
const { chatLimiter } = require('../middleware/rateLimiter');
const { chatValidator } = require('../middleware/chatValidators');

const router = express.Router();

/**
 * The chatbot - /api/v1/chat (2026-10-09).
 *
 * Signed-in users only, then the per-USER chat budget (`chatLimiter`, keyed on
 * the user, so it must come after `protect`), then input validation.
 */
router.use(protect);
router.use(chatLimiter);

router.post('/', validate(chatValidator), chatController.ask);

module.exports = router;
