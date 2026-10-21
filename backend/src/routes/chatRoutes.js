'use strict';

const express = require('express');

const chatController = require('../controllers/chatController');
const validate = require('../middleware/validate');
const { protect } = require('../middleware/auth');
const { chatLimiter } = require('../middleware/rateLimiter');
const { chatValidator } = require('../middleware/chatValidators');

const router = express.Router();

router.use(protect);
router.use(chatLimiter);

router.post('/', validate(chatValidator), chatController.ask);

module.exports = router;
