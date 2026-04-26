import express from "express";

const app = express();
const router = express.Router();

app.get("/health", (req, res) => {
    res.json({ status: "ok" });
});

app.post("/users", (req, res) => {
    res.json({ created: true });
});

router.get("/users/:id", (req, res) => {
    res.json({ id: req.params.id });
});

router.put("/users/:id", (req, res) => {
    res.json({ updated: true });
});
