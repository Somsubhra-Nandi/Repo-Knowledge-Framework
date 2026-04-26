import { readFileSync } from "fs";
import path from "path";

interface Processor {
    process(input: string): string;
}

class DataService implements Processor {
    private name: string;

    constructor(name: string) {
        this.name = name;
    }

    process(input: string): string {
        return this.formatOutput(input);
    }

    private formatOutput(value: string): string {
        return `${this.name}: ${value}`;
    }
}

class FileService {
    readFile(filePath: string): string {
        return readFileSync(filePath, "utf-8");
    }

    getBasename(filePath: string): string {
        return path.basename(filePath);
    }
}

function topLevelHelper(text: string): string {
    return text.trim();
}

const processText = (input: string): string => {
    return topLevelHelper(input);
};
