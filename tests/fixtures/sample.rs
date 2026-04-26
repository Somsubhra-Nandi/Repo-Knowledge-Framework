use std::collections::HashMap;
use std::fmt;

struct UserService {
    name: String,
}

struct Config {
    debug: bool,
}

trait Processor {
    fn process(&self, input: &str) -> String;
}

impl UserService {
    fn new(name: String) -> Self {
        UserService { name }
    }

    fn get_user(&self, id: &str) -> String {
        self.format_user(id)
    }

    fn format_user(&self, id: &str) -> String {
        format!("{}: {}", self.name, id)
    }
}

impl Processor for UserService {
    fn process(&self, input: &str) -> String {
        self.get_user(input)
    }
}

fn top_level_helper(text: &str) -> String {
    text.trim().to_string()
}

fn create_map() -> HashMap<String, String> {
    let mut map = HashMap::new();
    map.insert(top_level_helper("key"), String::from("value"));
    map
}
