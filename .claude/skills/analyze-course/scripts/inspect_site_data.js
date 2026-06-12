#!/usr/bin/env node
"use strict";

const fs = require("fs");
const vm = require("vm");

const file = process.argv[2];
if (!file) {
  process.stderr.write("data.js path is required\n");
  process.exit(2);
}

try {
  const source = fs.readFileSync(file, "utf8");
  const context = { window: {} };
  vm.runInNewContext(source, context, { timeout: 3000, filename: file });
  const data = context.window.EXAM_DATA;
  if (!data || !Array.isArray(data.lectures)) {
    throw new Error("window.EXAM_DATA.lectures is missing");
  }

  let questions = 0;
  let cards = 0;
  let invalidChoices = 0;
  let duplicateChoices = 0;
  let invalidAnswers = 0;

  for (const lecture of data.lectures) {
    const lectureQuestions = Array.isArray(lecture.questions) ? lecture.questions : [];
    const lectureCards = Array.isArray(lecture.cards)
      ? lecture.cards
      : (Array.isArray(lecture.mustKnow) ? lecture.mustKnow : []);
    questions += lectureQuestions.length;
    cards += lectureCards.length;

    for (const question of lectureQuestions) {
      if (Array.isArray(question)) {
        invalidChoices += 1;
        continue;
      }
      const choices = question.choices;
      if (!Array.isArray(choices) || choices.length !== 4) {
        invalidChoices += 1;
        continue;
      }
      if (new Set(choices.map((value) => String(value).trim())).size !== 4) {
        duplicateChoices += 1;
      }
      if (!Number.isInteger(question.answer) || question.answer < 0 || question.answer > 3) {
        invalidAnswers += 1;
      }
    }
  }

  process.stdout.write(JSON.stringify({
    parsed: true,
    lectures: data.lectures.length,
    questions,
    cards,
    invalid_choices: invalidChoices,
    duplicate_choices: duplicateChoices,
    invalid_answers: invalidAnswers
  }));
} catch (error) {
  process.stdout.write(JSON.stringify({ parsed: false, error: String(error.message || error) }));
  process.exitCode = 1;
}
