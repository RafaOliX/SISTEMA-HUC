-- phpMyAdmin SQL Dump
-- version 5.2.1
-- https://www.phpmyadmin.net/
--
-- Host: 127.0.0.1
-- Generation Time: Oct 21, 2025 at 02:55 PM
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
  `tipo` varchar(100) NOT NULL,
  `cedula` varchar(20) NOT NULL,
  `correo` varchar(100) NOT NULL,
  `telefono` varchar(20) NOT NULL,
  `foto` varchar(255) DEFAULT NULL,
  `fecha_ingreso` date NOT NULL DEFAULT curdate()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `enfermeros`
--

INSERT INTO `enfermeros` (`id`, `nombre`, `tipo`, `cedula`, `correo`, `telefono`, `foto`, `fecha_ingreso`) VALUES
(8, 'Sofia Ana Veracruz Martinez', 'circulante', 'V-23456789', 'maria.gomez@gmail.com', '0414-5864387', 'enfermero_Sofia_Ana_Veracruz_Martinez_V-23456789/OIP.webp', '2025-10-20'),
(9, 'Rauldy Josefina Silva Rodriguez', 'enfermera instrumentista', 'V-16556362', 'RauldySilva@gmail.com', '0412-6066030', 'enfermero_V-16556362/IMG-20251020-WA0104.jpg', '2025-10-20');

-- --------------------------------------------------------

--
-- Table structure for table `equipos_medicos`
--

CREATE TABLE `equipos_medicos` (
  `id` bigint(20) NOT NULL,
  `medico_id` bigint(20) NOT NULL,
  `nombre_equipo` varchar(255) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `equipo_enfermeros`
--

CREATE TABLE `equipo_enfermeros` (
  `equipo_id` bigint(20) NOT NULL,
  `enfermero_id` bigint(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `historial`
--

CREATE TABLE `historial` (
  `id` bigint(20) NOT NULL,
  `tipo` varchar(50) DEFAULT NULL,
  `entidad_id` bigint(20) DEFAULT NULL,
  `accion` varchar(100) DEFAULT NULL,
  `descripcion` text DEFAULT NULL,
  `usuario` varchar(100) DEFAULT NULL,
  `fecha` timestamp NOT NULL DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

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
  `cedula` varchar(20) NOT NULL,
  `fecha_ingreso` date NOT NULL DEFAULT curdate(),
  `foto` varchar(255) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `medicos`
--

INSERT INTO `medicos` (`id`, `nombre`, `especialidad`, `correo`, `telefono`, `cedula`, `fecha_ingreso`, `foto`) VALUES
(7, 'Jose Antonio Olivares Romero', 'Ingeniero Civil', 'jantonio@gmail.com', '0424-2375852', 'V-20564852', '2025-10-20', 'medico_Jose_Antonio_Olivares_Romero_V-20564852/400w-dSKgFIvN4iM.webp'),
(9, 'Pedro Jose Gutierrez Hernandez', 'CIRUGÍA DE CABEZA Y CUELLO', 'pgutierrez@gmail.com', '0414-6668985', 'V-25845975', '2025-10-20', 'medico_Pedro_Jose_Gutierrez_Hernandez_V-25845975/OIP.webp'),
(12, 'Pablo Martinez Hernandez Rondon', 'CIRUGÍA PARA PERROS', 'pmartinez@gmail.com', '0414-7898586', 'V-22344565', '2025-10-20', 'medico_Pablo_Martinez_Hernandez_Rondon_V-22344565/d698e40a01d77ed5e3394851338a4c5c.jpg'),
(13, 'Ofelia Maria Sanchez', 'Oftalmologia', 'ofesan123@gmail.com', '0414-99077880', 'V-9678054', '2025-10-20', 'medico_Ofelia_Maria_Sanchez_V-9678054/to-co-najcenniejsze.jpg'),
(14, 'Esther Karla Rodriguez Gonzalez', 'Cardiologa', 'Erodriguez@gmail.com', '0412-34567890', 'V-6789543', '2025-10-20', 'medico_Esther_Karla_Rodriguez_Gonzalez_V-6789543/The-Importance-of-Medical-Credentialing-Services-in-the-Year-2024-1024x725.jpg');

-- --------------------------------------------------------

--
-- Table structure for table `pacientes`
--

CREATE TABLE `pacientes` (
  `id` bigint(20) NOT NULL,
  `nombre_completo` varchar(255) NOT NULL,
  `cedula` varchar(20) NOT NULL,
  `telefono` varchar(20) NOT NULL,
  `edad` int(3) NOT NULL,
  `fecha_nacimiento` date NOT NULL,
  `tipo_sangre` varchar(5) NOT NULL,
  `motivo_cirugia` text NOT NULL,
  `equipo_id` bigint(20) DEFAULT NULL,
  `estado_atencion` enum('pendiente','atendido','validado','cancelado') DEFAULT 'pendiente',
  `resultado_final` varchar(100) DEFAULT NULL,
  `departamento` varchar(100) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Dumping data for table `pacientes`
--

INSERT INTO `pacientes` (`id`, `nombre_completo`, `cedula`, `telefono`, `edad`, `fecha_nacimiento`, `tipo_sangre`, `motivo_cirugia`, `equipo_id`, `estado_atencion`, `resultado_final`, `departamento`) VALUES
(35, 'Oscar Lozano', 'V-12567890', '0414 4206776', 60, '1920-03-23', 'A+', 'Rinoplastia', NULL, 'validado', 'Requiere intervención', 'Cirugía Plástica'),
(36, 'Oscar Lozano', 'V-4567890', '0414 4206776', 60, '1970-10-14', 'A+', 'Rinoplastia', NULL, 'pendiente', NULL, 'Cirugía Plástica');

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
(3, 'Garfio', '007', 'administrador', 'XRRYBYRIB4ERNAA5WZIA77SDZDX3X6OR'),
(4, 'usuario', '1234', 'usuario', 'G5JO6D6PYSBGIIEZSEV4ZDRH7BUBWNJJ');

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
-- Indexes for table `historial`
--
ALTER TABLE `historial`
  ADD PRIMARY KEY (`id`);

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
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=10;

--
-- AUTO_INCREMENT for table `equipos_medicos`
--
ALTER TABLE `equipos_medicos`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=4;

--
-- AUTO_INCREMENT for table `historial`
--
ALTER TABLE `historial`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `historial_uso`
--
ALTER TABLE `historial_uso`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=21;

--
-- AUTO_INCREMENT for table `medicos`
--
ALTER TABLE `medicos`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=15;

--
-- AUTO_INCREMENT for table `pacientes`
--
ALTER TABLE `pacientes`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=37;

--
-- AUTO_INCREMENT for table `salas_quirofano`
--
ALTER TABLE `salas_quirofano`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=17;

--
-- AUTO_INCREMENT for table `usuarios`
--
ALTER TABLE `usuarios`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=5;

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
