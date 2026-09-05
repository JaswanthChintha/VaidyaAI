'use strict';

const express = require('express');

const profileController = require('../controllers/profileController');
const validate = require('../middleware/validate');
const { protect } = require('../middleware/auth');
const { profileValidator } = require('../middleware/profileValidators');

const router = express.Router();

// Every profile route is authenticated. There is deliberately NO route that
// takes a profile id or a user id: the caller can only ever address their own
// profile, which removes the whole class of "change the id in the URL" attacks.
router.use(protect);

router
  .route('/me')
  .get(profileController.getMyProfile)
  .post(validate(profileValidator), profileController.createMyProfile)
  .put(validate(profileValidator), profileController.replaceMyProfile)
  .patch(validate(profileValidator), profileController.updateMyProfile)
  .delete(profileController.deleteMyProfile);

module.exports = router;
