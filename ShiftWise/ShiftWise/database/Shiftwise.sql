CREATE TABLE `Company` (
  `id` bigint PRIMARY KEY,
  `name` varchar(255),
  `open_time` time COMMENT 'hours of operation, same every day (default 08:00)',
  `close_time` time COMMENT 'hours of operation, same every day (default 18:00)',
  `created_at` timestamptz,
  `modified_at` timestamptz
);

CREATE TABLE `Department` (
  `id` bigint PRIMARY KEY,
  `company_id` bigint,
  `name` varchar(255),
  `created_at` timestamptz,
  `modified_at` timestamptz
);

CREATE TABLE `User` (
  `id` bigint PRIMARY KEY,
  `first_name` varchar(255),
  `last_name` varchar(255),
  `username` varchar(255),
  `email` varchar(255) UNIQUE COMMENT 'Login Identifier',
  `password` varchar(255),
  `date_of_birth` timestamptz,
  `is_active` boolean COMMENT 'Deactivated users cant log in',
  `created_at` timestamptz
);

CREATE TABLE `Compatibility Group` (
  `id` bigint PRIMARY KEY,
  `company_id` bigint,
  `score` smallint COMMENT '1-10: how well this group of 2+ employees work together',
  `rated_by_id` bigint COMMENT 'User',
  `created_at` timestamptz,
  `updated_at` timestamptz
);

CREATE TABLE `Compatibility Group Member` (
  `id` bigint PRIMARY KEY,
  `compatibility_group_id` bigint,
  `employee_profile_id` bigint
);

CREATE TABLE `Shift` (
  `id` bigint PRIMARY KEY,
  `department_id` bigint,
  `name` varchar(100),
  `shift_date` date,
  `start_time` time,
  `end_time` time,
  `headcount` int COMMENT 'how many people are needed (1-100)',
  `created_by_id` bigint,
  `created_at` timestamptz
);

CREATE TABLE `Shift Template` (
  `id` bigint PRIMARY KEY,
  `company_id` bigint,
  `name` varchar(100),
  `start_time` time,
  `end_time` time,
  `headcount` int,
  `created_by_id` bigint
);

CREATE TABLE `Shift Request` (
  `id` bigint PRIMARY KEY,
  `kind` ENUM ('give', 'take', 'swap'),
  `requester_id` bigint,
  `target_id` bigint,
  `schedule_id` bigint COMMENT 'the assignment being given/taken/swapped',
  `other_schedule_id` bigint COMMENT 'the other assignment (swap only)',
  `status` ENUM ('pending', 'accepted', 'declined', 'cancelled'),
  `created_at` timestamptz,
  `resolved_at` timestamptz
);

CREATE TABLE `Schedule` (
  `id` bigint PRIMARY KEY,
  `shift_id` bigint COMMENT 'set when this row is a person assigned to a Shift',
  `task_name` varchar(255),
  `employee_id` bigint,
  `shift_date` date,
  `start_time` time,
  `end_time` time,
  `status` ENUM ('Scheduled', 'Completed', 'Cancelled') COMMENT 'Scheduled, Completed, Cancelled',
  `notes` text COMMENT 'optional instructions or remarks',
  `created_at` timestamptz,
  `modified_at` timestamptz
);

CREATE TABLE `Employee Profile` (
  `id` bigint PRIMARY KEY,
  `user_id` bigint,
  `company_id` varchar(255),
  `department_id` bigint,
  `role` ENUM ('CEO', 'Manager', 'Employee'),
  `employment_type` ENUM ('Full time', 'Part time') COMMENT 'full time: 40 hrs/week, part time: 5-39',
  `allow_overtime` boolean COMMENT 'full time only: may be scheduled over 40 hours',
  `position` varchar(255),
  `productivity_score` decimal COMMENT 'Individual rank/ score used by the solver',
  `pay_rate` decimal COMMENT 'optional',
  `created_at` timestamptz,
  `modified_at` timestamptz
);

CREATE TABLE `Availability Slot` (
  `id` bigint PRIMARY KEY,
  `employee_id` bigint,
  `day_of_week` smallint COMMENT '0-6',
  `start_time` time,
  `end_time` time
);

CREATE TABLE `Compatibility Scoring` (
  `id` bigint PRIMARY KEY,
  `employee_a_id` bigint COMMENT 'Lower id of the pair',
  `employee_b_id` bigint COMMENT 'Higher id of the pair',
  `score` decimal COMMENT 'E.g. 1-10, 1=avoid scheduling together',
  `rated_by` bigint COMMENT 'optional'
);

CREATE TABLE `Time-off Requests` (
  `id` bigint PRIMARY KEY,
  `employee_id` bigint,
  `start_date` date,
  `end_date` date,
  `reason` text COMMENT 'optional',
  `status` ENUM ('Pending', 'Approved', 'Denied'),
  `requested_at` timestamptz
);

CREATE TABLE `Project` (
  `id` bigint PRIMARY KEY,
  `company_id` bigint,
  `department_id` bigint COMMENT 'optional',
  `name` varchar(255),
  `description` text COMMENT 'optional',
  `priority` ENUM ('High', 'Medium', 'Low'),
  `is_active` boolean,
  `created_at` timestamptz,
  `modified_at` timestamptz
);

ALTER TABLE `Department` ADD FOREIGN KEY (`company_id`) REFERENCES `Company` (`id`);

ALTER TABLE `Employee Profile` ADD FOREIGN KEY (`user_id`) REFERENCES `User` (`id`);

ALTER TABLE `Employee Profile` ADD FOREIGN KEY (`department_id`) REFERENCES `Department` (`id`);

CREATE TABLE `Manager Department` (
  `id` bigint PRIMARY KEY,
  `employee_profile_id` bigint COMMENT 'A manager',
  `department_id` bigint COMMENT 'A department that manager runs (a manager can run several, a department can have several managers)'
);

CREATE TABLE `Join Code` (
  `id` bigint PRIMARY KEY,
  `code` varchar(12) UNIQUE COMMENT 'Single use, e.g. ABCD-2345',
  `company_id` bigint,
  `role` ENUM ('Manager', 'Employee') COMMENT 'What the person who uses it becomes',
  `created_by_id` bigint COMMENT 'User who made the code',
  `used_by_id` bigint COMMENT 'Empty until someone uses the code',
  `created_at` timestamptz,
  `used_at` timestamptz
);

CREATE TABLE `Join Code Department` (
  `id` bigint PRIMARY KEY,
  `join_code_id` bigint,
  `department_id` bigint COMMENT 'Employee code: exactly one. Manager code: one or more.'
);

CREATE TABLE `Transfer Request` (
  `id` bigint PRIMARY KEY,
  `employee_id` bigint COMMENT 'Employee Profile being moved',
  `from_department_id` bigint,
  `to_department_id` bigint,
  `requested_by_id` bigint COMMENT 'User who asked for the move',
  `status` ENUM ('Pending', 'Accepted', 'Rejected'),
  `resolved_by_id` bigint,
  `created_at` timestamptz,
  `resolved_at` timestamptz
);

CREATE TABLE `Notification` (
  `id` bigint PRIMARY KEY,
  `recipient_id` bigint COMMENT 'User',
  `kind` ENUM ('Transfer request', 'Transfer result', 'No manager', 'Info', 'Shift request'),
  `message` varchar(500),
  `transfer_request_id` bigint,
  `shift_request_id` bigint,
  `is_read` boolean,
  `created_at` timestamptz
);

ALTER TABLE `Availability Slot` ADD FOREIGN KEY (`employee_id`) REFERENCES `Employee Profile` (`id`);

ALTER TABLE `Compatibility Scoring` ADD FOREIGN KEY (`employee_a_id`) REFERENCES `Employee Profile` (`id`);

ALTER TABLE `Compatibility Scoring` ADD FOREIGN KEY (`employee_b_id`) REFERENCES `Employee Profile` (`id`);

ALTER TABLE `Time-off Requests` ADD FOREIGN KEY (`employee_id`) REFERENCES `Employee Profile` (`id`);

ALTER TABLE `Project` ADD FOREIGN KEY (`company_id`) REFERENCES `Company` (`id`);

ALTER TABLE `Employee Profile` ADD FOREIGN KEY (`company_id`) REFERENCES `Company` (`id`);

ALTER TABLE `Project` ADD FOREIGN KEY (`department_id`) REFERENCES `Department` (`id`);

ALTER TABLE `Schedule` ADD FOREIGN KEY (`employee_id`) REFERENCES `Employee Profile` (`id`);

ALTER TABLE `Schedule` ADD FOREIGN KEY (`shift_id`) REFERENCES `Shift` (`id`);

ALTER TABLE `Compatibility Group` ADD FOREIGN KEY (`company_id`) REFERENCES `Company` (`id`);

ALTER TABLE `Compatibility Group` ADD FOREIGN KEY (`rated_by_id`) REFERENCES `User` (`id`);

ALTER TABLE `Compatibility Group Member` ADD FOREIGN KEY (`compatibility_group_id`) REFERENCES `Compatibility Group` (`id`);

ALTER TABLE `Compatibility Group Member` ADD FOREIGN KEY (`employee_profile_id`) REFERENCES `Employee Profile` (`id`);

ALTER TABLE `Shift` ADD FOREIGN KEY (`department_id`) REFERENCES `Department` (`id`);

ALTER TABLE `Shift` ADD FOREIGN KEY (`created_by_id`) REFERENCES `Employee Profile` (`id`);

ALTER TABLE `Shift Template` ADD FOREIGN KEY (`company_id`) REFERENCES `Company` (`id`);

ALTER TABLE `Shift Template` ADD FOREIGN KEY (`created_by_id`) REFERENCES `Employee Profile` (`id`);

ALTER TABLE `Shift Request` ADD FOREIGN KEY (`requester_id`) REFERENCES `Employee Profile` (`id`);

ALTER TABLE `Shift Request` ADD FOREIGN KEY (`target_id`) REFERENCES `Employee Profile` (`id`);

ALTER TABLE `Shift Request` ADD FOREIGN KEY (`schedule_id`) REFERENCES `Schedule` (`id`);

ALTER TABLE `Shift Request` ADD FOREIGN KEY (`other_schedule_id`) REFERENCES `Schedule` (`id`);

ALTER TABLE `Notification` ADD FOREIGN KEY (`shift_request_id`) REFERENCES `Shift Request` (`id`);

ALTER TABLE `Manager Department` ADD FOREIGN KEY (`employee_profile_id`) REFERENCES `Employee Profile` (`id`);

ALTER TABLE `Manager Department` ADD FOREIGN KEY (`department_id`) REFERENCES `Department` (`id`);

ALTER TABLE `Join Code` ADD FOREIGN KEY (`company_id`) REFERENCES `Company` (`id`);

ALTER TABLE `Join Code` ADD FOREIGN KEY (`created_by_id`) REFERENCES `User` (`id`);

ALTER TABLE `Join Code` ADD FOREIGN KEY (`used_by_id`) REFERENCES `User` (`id`);

ALTER TABLE `Join Code Department` ADD FOREIGN KEY (`join_code_id`) REFERENCES `Join Code` (`id`);

ALTER TABLE `Join Code Department` ADD FOREIGN KEY (`department_id`) REFERENCES `Department` (`id`);

ALTER TABLE `Transfer Request` ADD FOREIGN KEY (`employee_id`) REFERENCES `Employee Profile` (`id`);

ALTER TABLE `Transfer Request` ADD FOREIGN KEY (`from_department_id`) REFERENCES `Department` (`id`);

ALTER TABLE `Transfer Request` ADD FOREIGN KEY (`to_department_id`) REFERENCES `Department` (`id`);

ALTER TABLE `Transfer Request` ADD FOREIGN KEY (`requested_by_id`) REFERENCES `User` (`id`);

ALTER TABLE `Transfer Request` ADD FOREIGN KEY (`resolved_by_id`) REFERENCES `User` (`id`);

ALTER TABLE `Notification` ADD FOREIGN KEY (`recipient_id`) REFERENCES `User` (`id`);

ALTER TABLE `Notification` ADD FOREIGN KEY (`transfer_request_id`) REFERENCES `Transfer Request` (`id`);
