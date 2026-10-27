CREATE TABLE `Company` (
  `id` bigint PRIMARY KEY,
  `name` varchar(255),
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

CREATE TABLE `Schedule` (
  `id` bigint PRIMARY KEY,
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

ALTER TABLE `Availability Slot` ADD FOREIGN KEY (`employee_id`) REFERENCES `Employee Profile` (`id`);

ALTER TABLE `Compatibility Scoring` ADD FOREIGN KEY (`employee_a_id`) REFERENCES `Employee Profile` (`id`);

ALTER TABLE `Compatibility Scoring` ADD FOREIGN KEY (`employee_b_id`) REFERENCES `Employee Profile` (`id`);

ALTER TABLE `Time-off Requests` ADD FOREIGN KEY (`employee_id`) REFERENCES `Employee Profile` (`id`);

ALTER TABLE `Project` ADD FOREIGN KEY (`company_id`) REFERENCES `Company` (`id`);

ALTER TABLE `Employee Profile` ADD FOREIGN KEY (`company_id`) REFERENCES `Company` (`id`);

ALTER TABLE `Project` ADD FOREIGN KEY (`department_id`) REFERENCES `Department` (`id`);

ALTER TABLE `Schedule` ADD FOREIGN KEY (`employee_id`) REFERENCES `Employee Profile` (`id`);
