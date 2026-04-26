const fs = require("fs");
const path = require("path");

class Calculator {
    add(a, b) {
        return this.validate(a) + this.validate(b);
    }

    validate(value) {
        return typeof value === "number" ? value : 0;
    }
}

class FileHelper {
    readFile(filePath) {
        return fs.readFileSync(filePath, "utf-8");
    }
}

function formatResult(value) {
    return String(value);
}

const doubleValue = (x) => {
    return formatResult(x * 2);
};
