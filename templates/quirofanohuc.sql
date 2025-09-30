-- phpMyAdmin SQL Dump
-- version 5.2.1
-- https://www.phpmyadmin.net/
--
-- Host: 127.0.0.1
-- Generation Time: Aug 09, 2025 at 04:17 PM
-- Server version: 10.4.32-MariaDB
-- PHP Version: 8.2.12

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Database: `quirofanohuc`
--

-- --------------------------------------------------------

--
-- Table structure for table `enfermeros`
--

CREATE TABLE `enfermeros` (
  `id` bigint(20) NOT NULL,
  `nombre` varchar(255) NOT NULL,
  `tipo` enum('anestesiólogo','instrumentista','circulante','asistente','jefe de enfermería') NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `enfermeros`
--

INSERT INTO `enfermeros` (`id`, `nombre`, `tipo`) VALUES
(1, 'negra', 'jefe de enfermería'),
(2, 'panqueca', 'anestesiólogo'),
(3, 'beto', 'instrumentista');

-- --------------------------------------------------------

--
-- Table structure for table `equipos_medicos`
--

CREATE TABLE `equipos_medicos` (
  `id` bigint(20) NOT NULL,
  `medico_id` bigint(20) NOT NULL,
  `nombre_equipo` varchar(255) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `equipos_medicos`
--

INSERT INTO `equipos_medicos` (`id`, `medico_id`, `nombre_equipo`) VALUES
(1, 1, 'ATILA EQUIPO'),
(2, 2, 'Garfio equipo');

-- --------------------------------------------------------

--
-- Table structure for table `equipo_enfermeros`
--

CREATE TABLE `equipo_enfermeros` (
  `equipo_id` bigint(20) NOT NULL,
  `enfermero_id` bigint(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `equipo_enfermeros`
--

INSERT INTO `equipo_enfermeros` (`equipo_id`, `enfermero_id`) VALUES
(1, 1),
(1, 2),
(2, 3);

-- --------------------------------------------------------

--
-- Table structure for table `historial_uso`
--

CREATE TABLE `historial_uso` (
  `id` bigint(20) NOT NULL,
  `sala_id` bigint(20) DEFAULT NULL,
  `medico_id` bigint(20) DEFAULT NULL,
  `fecha_uso` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `duracion` time NOT NULL,
  `descripcion` varchar(255) DEFAULT ''
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `historial_uso`
--

INSERT INTO `historial_uso` (`id`, `sala_id`, `medico_id`, `fecha_uso`, `duracion`, `descripcion`) VALUES
(1, 11, NULL, '2025-06-22 18:04:30', '00:00:00', 'Modificación de sala por Garfio'),
(2, 12, NULL, '2025-06-22 18:08:48', '00:00:00', 'Modificación de sala por Garfio'),
(3, 11, NULL, '2025-06-22 18:12:50', '00:00:00', 'Modificación de sala por Garfio'),
(4, 12, 1, '2025-07-26 18:30:08', '00:00:00', 'Fallecido en Quirófano'),
(5, 11, 1, '2025-07-26 23:33:04', '00:00:00', 'Operación Exitosa'),
(6, 11, 1, '2025-07-26 23:34:43', '00:00:00', 'Operación Exitosa'),
(7, 6, 2, '2025-07-27 22:34:20', '00:00:00', 'Operación Exitosa'),
(8, 6, 2, '2025-07-27 22:39:02', '00:00:00', 'Operación cancelada'),
(9, 11, 1, '2025-07-27 22:49:58', '00:02:00', 'Operación cancelada'),
(10, 11, 1, '2025-07-27 22:52:10', '00:01:00', 'Operación Exitosa'),
(11, 12, 2, '2025-07-27 22:52:19', '02:00:00', 'Operación Exitosa'),
(12, 11, 1, '2025-07-28 00:05:36', '00:04:00', 'Operación Exitosa'),
(13, 11, 1, '2025-07-28 00:08:06', '00:00:00', 'Operación Exitosa'),
(14, 6, 1, '2025-07-28 00:17:02', '01:00:00', 'Operación Exitosa'),
(15, 11, 1, '2025-07-28 00:20:36', '00:01:00', 'Traslado a cuidados intensivos'),
(16, 11, 1, '2025-08-09 13:57:40', '01:00:00', 'Operación Exitosa');

-- --------------------------------------------------------

--
-- Table structure for table `medicos`
--

CREATE TABLE `medicos` (
  `id` bigint(20) NOT NULL,
  `nombre` text NOT NULL,
  `especialidad` text NOT NULL,
  `correo` varchar(100) NOT NULL,
  `telefono` varchar(20) NOT NULL,
  `cedula` varchar(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `medicos`
--

INSERT INTO `medicos` (`id`, `nombre`, `especialidad`, `correo`, `telefono`, `cedula`) VALUES
(1, 'ATILA', 'GATO', 'ATILA@GMAIL.COM', '0416', '01'),
(2, 'Gzrfio', 'Oftalmo', 'garfio07@gmail.com', '0416', '4444');

-- --------------------------------------------------------

--
-- Table structure for table `pacientes`
--

CREATE TABLE `pacientes` (
  `id` bigint(20) NOT NULL,
  `nombre_completo` varchar(255) NOT NULL,
  `edad` int(3) NOT NULL,
  `fecha_nacimiento` date NOT NULL,
  `tipo_sangre` varchar(5) NOT NULL,
  `motivo_cirugia` text NOT NULL,
  `equipo_id` bigint(20) DEFAULT NULL,
  `estado_atencion` enum('pendiente','atendido','validado','cancelado') DEFAULT 'pendiente',
  `resultado_final` varchar(100) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `pacientes`
--

INSERT INTO `pacientes` (`id`, `nombre_completo`, `edad`, `fecha_nacimiento`, `tipo_sangre`, `motivo_cirugia`, `equipo_id`, `estado_atencion`, `resultado_final`) VALUES
(1, 'Juan Pérez', 45, '1980-06-15', 'O+', 'Apendicitis aguda', NULL, 'validado', 'Traslado a cuidados intensivos'),
(3, 'Rihabel Padilla', 22, '2003-06-20', 'O+', 'oftalmo', NULL, 'validado', 'Operación Exitosa');

-- --------------------------------------------------------

--
-- Table structure for table `salas_quirofano`
--

CREATE TABLE `salas_quirofano` (
  `id` bigint(20) NOT NULL,
  `estado` enum('en uso','mantenimiento','libre') NOT NULL,
  `x` int(11) DEFAULT 0,
  `y` int(11) DEFAULT 0,
  `equipo_id` bigint(20) DEFAULT NULL,
  `paciente_id` bigint(20) DEFAULT NULL,
  `hora_inicio` time DEFAULT NULL,
  `hora_fin` time DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `salas_quirofano`
--

INSERT INTO `salas_quirofano` (`id`, `estado`, `x`, `y`, `equipo_id`, `paciente_id`, `hora_inicio`, `hora_fin`) VALUES
(6, 'libre', 60, 60, NULL, NULL, NULL, NULL),
(7, 'libre', 160, 60, NULL, NULL, NULL, NULL),
(8, 'libre', 260, 60, NULL, NULL, NULL, NULL),
(9, 'libre', 360, 60, NULL, NULL, NULL, NULL),
(10, 'libre', 460, 60, NULL, NULL, NULL, NULL),
(11, 'libre', 60, 240, NULL, NULL, NULL, NULL),
(12, 'libre', 160, 240, NULL, NULL, NULL, NULL),
(13, 'libre', 260, 240, NULL, NULL, NULL, NULL),
(14, 'libre', 360, 240, NULL, NULL, NULL, NULL),
(15, 'libre', 460, 240, NULL, NULL, NULL, NULL);

-- --------------------------------------------------------

--
-- Table structure for table `usuarios`
--

CREATE TABLE `usuarios` (
  `id` bigint(20) NOT NULL,
  `nombre_usuario` text NOT NULL,
  `contraseña` text NOT NULL,
  `rol` enum('administrador','usuario') NOT NULL,
  `2AF` varchar(32) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `usuarios`
--

INSERT INTO `usuarios` (`id`, `nombre_usuario`, `contraseña`, `rol`, `2AF`) VALUES
(1, 'rafa', '1234', 'administrador', 'VL224NIKUIZAYM5VSWC2YKF5KVN5CYJS'),
(2, 'beto', '1', 'usuario', 'AFHS5XX4TRVLTWN4X37SXSDNHNU4OUSB'),
(3, 'Garfio', '007', 'administrador', 'XRRYBYRIB4ERNAA5WZIA77SDZDX3X6OR');

--
-- Indexes for dumped tables
--

--
-- Indexes for table `enfermeros`
--
ALTER TABLE `enfermeros`
  ADD PRIMARY KEY (`id`);

--
-- Indexes for table `equipos_medicos`
--
ALTER TABLE `equipos_medicos`
  ADD PRIMARY KEY (`id`),
  ADD KEY `medico_id` (`medico_id`);

--
-- Indexes for table `equipo_enfermeros`
--
ALTER TABLE `equipo_enfermeros`
  ADD PRIMARY KEY (`equipo_id`,`enfermero_id`),
  ADD KEY `enfermero_id` (`enfermero_id`);

--
-- Indexes for table `historial_uso`
--
ALTER TABLE `historial_uso`
  ADD PRIMARY KEY (`id`),
  ADD KEY `sala_id` (`sala_id`),
  ADD KEY `medico_id` (`medico_id`);

--
-- Indexes for table `medicos`
--
ALTER TABLE `medicos`
  ADD PRIMARY KEY (`id`);

--
-- Indexes for table `pacientes`
--
ALTER TABLE `pacientes`
  ADD PRIMARY KEY (`id`),
  ADD KEY `equipo_id` (`equipo_id`);

--
-- Indexes for table `salas_quirofano`
--
ALTER TABLE `salas_quirofano`
  ADD PRIMARY KEY (`id`);

--
-- Indexes for table `usuarios`
--
ALTER TABLE `usuarios`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `nombre_usuario` (`nombre_usuario`) USING HASH;

--
-- AUTO_INCREMENT for dumped tables
--

--
-- AUTO_INCREMENT for table `enfermeros`
--
ALTER TABLE `enfermeros`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=4;

--
-- AUTO_INCREMENT for table `equipos_medicos`
--
ALTER TABLE `equipos_medicos`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=3;

--
-- AUTO_INCREMENT for table `historial_uso`
--
ALTER TABLE `historial_uso`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=17;

--
-- AUTO_INCREMENT for table `medicos`
--
ALTER TABLE `medicos`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=3;

--
-- AUTO_INCREMENT for table `pacientes`
--
ALTER TABLE `pacientes`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=4;

--
-- AUTO_INCREMENT for table `salas_quirofano`
--
ALTER TABLE `salas_quirofano`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=17;

--
-- AUTO_INCREMENT for table `usuarios`
--
ALTER TABLE `usuarios`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=4;

--
-- Constraints for dumped tables
--

--
-- Constraints for table `equipos_medicos`
--
ALTER TABLE `equipos_medicos`
  ADD CONSTRAINT `equipos_medicos_ibfk_1` FOREIGN KEY (`medico_id`) REFERENCES `medicos` (`id`);

--
-- Constraints for table `equipo_enfermeros`
--
ALTER TABLE `equipo_enfermeros`
  ADD CONSTRAINT `equipo_enfermeros_ibfk_1` FOREIGN KEY (`equipo_id`) REFERENCES `equipos_medicos` (`id`),
  ADD CONSTRAINT `equipo_enfermeros_ibfk_2` FOREIGN KEY (`enfermero_id`) REFERENCES `enfermeros` (`id`);

--
-- Constraints for table `historial_uso`
--
ALTER TABLE `historial_uso`
  ADD CONSTRAINT `historial_uso_ibfk_1` FOREIGN KEY (`sala_id`) REFERENCES `salas_quirofano` (`id`),
  ADD CONSTRAINT `historial_uso_ibfk_2` FOREIGN KEY (`medico_id`) REFERENCES `medicos` (`id`);

--
-- Constraints for table `pacientes`
--
ALTER TABLE `pacientes`
  ADD CONSTRAINT `pacientes_ibfk_1` FOREIGN KEY (`equipo_id`) REFERENCES `equipos_medicos` (`id`);
COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
