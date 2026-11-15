// SYNTHETIC sample code for GigBid persona fullstack. provenance: personas@228603469f77
const express = require("express");
const { Job } = require("./models");

const router = express.Router();

router.get("/v1/jobs", async (req, res) => {
  const { status, page = 1 } = req.query;
  const jobs = await Job.find(status ? { status } : {})
    .sort({ updatedAt: -1 }).skip((page - 1) * 50).limit(50).lean();
  res.json({ data: jobs, page: Number(page) });
});

module.exports = router;
